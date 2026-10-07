"""
ABU Robocon 2027 — "The Pursuit of Mustika Nusantara"  (v2: ada MUSUH + BALIK KOTAK)

Tim MERAH (kamu, kiri)            Tim BIRU (musuh AI, kanan)
  TR = MANUAL                       TR = AI feeder (ambil blok -> antar ke Transfer)
  BR = AUTONOMOUS                   BR = AI builder (bangun menara, ambil Mustika,
                                         dan membalik kotak lawan)

Jalankan:  python robocon2027_game_v2.py   ->  pilih MODE & strategi, lalu tekan START (atau Enter).

DUA MODE (pilih sebelum START):
  MANUAL : kamu main sendiri sebagai tim MERAH. TR selalu kamu kendalikan. BR merah bisa
           otomatis (bantuan, default) atau kamu kendalikan juga (centang "BR merah manual"
           atau tekan B; ganti robot yang dikendalikan dengan TAB). Biru = bot lawan.
  AUTO   : bot vs bot. Kedua tim dimainkan AI, masing-masing dengan STRATEGI sendiri:
             RUSH     "Mustika Rush": bangun L1 lalu L2 secepatnya, langsung ambil Mustika.
             DISRUPT  "Disruptor": TR sering membalik menara lawan (menggagalkan syarat Mustika),
                      BR bangun banyak menara & "snipe" Mustika di 90 detik terakhir / saat lawan siap.
             BALANCED "Seimbang": sisi sendiri dulu (L1 + L2), baru spot tengah; Mustika begitu siap.

Kontrol (mode MANUAL, robot aktif = TR atau BR):
  Panah / WASD : gerak       SPASI : aksi robot aktif (TR: ambil/taruh ke Transfer;
                                   BR: ambil dari Transfer, taruh di menara, Mustika)
  TAB : ganti TR <-> BR (jika BR manual)
  F            : BALIK kotak lawan (blok paling atas menara lawan di dekatmu jadi milik merah)
  Klik kiri    : teleport TR
Umum:  START / Enter mulai | P pause | B BR merah auto ON/OFF | G BR merah ikut balik kotak (auto) | E musuh ON/OFF
       R reset | H label

ATURAN (yang dimodelkan)
  * Menara = 3 blok: Earth, Earth, Sky (tiap blok punya pemilik = tim yang menaruhnya).
  * Poin per blok: 10/20/40 untuk tingkat 1/2/3, spot L2 dikali 2 -> milik pemilik blok saat ini.
  * MUSTIKA: BR boleh LANGSUNG mengambil Mustika di pedestal & meletakkannya di tiang tengah
    (+250) begitu timnya punya menara selesai di L1 DAN di L2 (blok teratas = milik tim itu).
  * BALIK KOTAK: blok teratas menara lawan berubah jadi milik pembalik -> poin pindah, dan
    syarat menara/Mustika lawan bisa gugur.
      - BR (otomatis, kedua tim): jika di spot TENGAH (L1_SH_N / L1_SH_S, antara dua tim) ada
        tumpukan 3 kotak yang blok paling atasnya milik lawan, BR pergi ke sana dan membaliknya.
      - TR manual (F): jangkauan 1.3 m, cooldown 1 s.
CATATAN: ukuran lapangan 11.1 m, L1 6x6 m @0.6 m, pedestal Mustika, ramp 9.74 derajat, tangga
3 anak tangga dari repo nav27. Skor, kapasitas transfer (E3/S4) dan stok (E20/S6) mengikuti catatan
simulator ABU2027_Sim. Posisi gudang/spot PERKIRAAN — cocokkan dengan rulebook resmi.
"""

import heapq
import math
import time
import tkinter as tk
from collections import deque

# ═════════════════════════ KONFIGURASI (meter) ═════════════════════════
HALF = 5.55
L1_HALF, L1_H = 3.0, 0.60
L2_HALF, L2_H = 1.5, 0.925
L2_STEP_H = 0.76
BAND_X, BAND_Y = (3.0, 4.0), (-0.9, 0.1)
RAMP_Y, STAIR_Y = (0.1, 3.0), (-3.0, -0.9)
MUSTIKA_POS = (0.0, 4.25)
PED_WORK = (0.0, 3.25)                 # posisi berdiri untuk ambil Mustika (di pad utara)
REACH_PED, REACH_FLIP, REACH_TRANSFER, REACH_SRC = 1.3, 1.3, 1.2, 1.5
PILLAR_HALF = 0.2
ROBOT, MAX_STEP = 0.5, 0.25
TR_SPEED, BR_SPEED = 1.7, 1.3          # m/s
MATCH_TIME = 180.0                     # 3 menit (durasi standar ABU Robocon; cek rulebook 2027!)
COUNTDOWN = 3.0                        # hitung mundur setelah START (0 = langsung mulai)
ENEMY_SPEED = 0.8                      # kecepatan robot musuh (1.0 = sama dengan kita)
SNIPE_AT = 90.0                        # strategi snipe: ambil Mustika saat sisa waktu <= ini (detik)
MIDDLE_SPOTS = ("L1_SH_N", "L1_SH_S")      # spot TENGAH di antara dua tim
FLIP_TR_ANYWHERE = True                # True: TR manual (F) boleh balik di spot mana pun; False: aturan sama dgn BR
SKY_CENTER = (0.0, -4.45)
CAP = {"E": 3, "S": 4}
STOCK0 = {"E": 20, "S": 6}
SEQ = ["E", "E", "S"]
LEVEL_PTS = [10, 20, 40]
MUSTIKA_PTS = 250

SPOTS = {
    "L1_RS":   dict(pos=(-2.55, -2.55), work=(-2.0, -2.0),  mult=1, kind="L1"),
    "L1_RN":   dict(pos=(-2.55, 2.55),  work=(-2.0, 2.0),   mult=1, kind="L1"),
    "L1_BS":   dict(pos=(2.55, -2.55),  work=(2.0, -2.0),   mult=1, kind="L1"),
    "L1_BN":   dict(pos=(2.55, 2.55),   work=(2.0, 2.0),    mult=1, kind="L1"),
    "L1_SH_S": dict(pos=(0.0, -3.0),    work=(0.0, -2.5),   mult=1, kind="L1"),
    "L1_SH_N": dict(pos=(0.0, 3.0),     work=(0.0, 2.5),    mult=1, kind="L1"),
    "L2_SW":   dict(pos=(-1.1, -1.1),   work=(-0.75, -0.75), mult=2, kind="L2"),
    "L2_NW":   dict(pos=(-1.1, 1.1),    work=(-0.75, 0.75), mult=2, kind="L2"),
    "L2_SE":   dict(pos=(1.1, -1.1),    work=(0.75, -0.75), mult=2, kind="L2"),
    "L2_NE":   dict(pos=(1.1, 1.1),     work=(0.75, 0.75),  mult=2, kind="L2"),
}
# token urutan bangun, diterjemahkan per tim (s=selatan, n=utara, M=spot tengah, o=sisi lawan)
TOKENS = {
    "red":  dict(L1s="L1_RS", L1n="L1_RN", L2s="L2_SW", L2n="L2_NW",
                 Ms="L1_SH_S", Mn="L1_SH_N", oL2s="L2_SE", oL2n="L2_NE"),
    "blue": dict(L1s="L1_BS", L1n="L1_BN", L2s="L2_SE", L2n="L2_NE",
                 Ms="L1_SH_N", Mn="L1_SH_S", oL2s="L2_SW", oL2n="L2_NW"),
}
STRATEGIES = {
    "RUSH": dict(
        label="Mustika Rush", desc="L1+L2 secepatnya, Mustika langsung",
        order=["L1s", "L2s", "Ms", "L1n", "L2n", "Mn", "oL2s", "oL2n"],
        mustika="asap", flip_start=60.0, flip_cd=25.0,
        tr_flip=False, tr_flip_start=0.0, tr_flip_cd=0.0),
    "DISRUPT": dict(
        label="Disruptor", desc="TR ganggu menara lawan, Mustika snipe",
        order=["L1s", "Ms", "L2s", "L1n", "Mn", "L2n", "oL2s", "oL2n"],
        mustika="snipe", flip_start=10.0, flip_cd=12.0,
        tr_flip=True, tr_flip_start=25.0, tr_flip_cd=18.0),
    "BALANCED": dict(
        label="Seimbang", desc="sisi sendiri dulu, lalu tengah",
        order=["L1s", "L2s", "L1n", "L2n", "Ms", "Mn", "oL2s", "oL2n"],
        mustika="asap", flip_start=30.0, flip_cd=20.0,
        tr_flip=False, tr_flip_start=0.0, tr_flip_cd=0.0),
}


def resolve_order(key, team):
    return [TOKENS[team][tok] for tok in STRATEGIES[key]["order"]]
# ═══════════════════════════════════════════════════════════════════════


def height(x, y):
    if abs(x) > HALF or abs(y) > HALF:
        return None
    if abs(x) <= L2_HALF and abs(y) <= L2_HALF:
        return L2_H
    if L2_HALF < abs(x) <= L2_HALF + 0.6 and -0.6 <= y <= 0.7:
        return L2_STEP_H
    if abs(x) <= L1_HALF and abs(y) <= L1_HALF:
        return L1_H
    if abs(x) <= 0.75 and L1_HALF < abs(y) <= 3.5:
        return L1_H
    if BAND_X[0] < abs(x) <= BAND_X[1]:
        if BAND_Y[0] <= y <= BAND_Y[1]:
            return L1_H
        if RAMP_Y[0] < y <= RAMP_Y[1]:
            return L1_H * (RAMP_Y[1] - y) / (RAMP_Y[1] - RAMP_Y[0])
        if STAIR_Y[0] <= y < BAND_Y[0]:
            n = int((y - STAIR_Y[0]) / ((BAND_Y[0] - STAIR_Y[0]) / 3)) + 1
            return L1_H / 3 * min(n, 3)
    return 0.0


def solid(x, y):
    h = ROBOT / 2
    if abs(x) < PILLAR_HALF + h and abs(y) < PILLAR_HALF + h:
        return True
    return abs(x - MUSTIKA_POS[0]) < 0.25 + h and abs(y - MUSTIKA_POS[1]) < 0.25 + h


def can_stand(x, y, cur_h):
    if solid(x, y):
        return False
    r = ROBOT / 2
    for ox in (-r, 0, r):
        for oy in (-r, 0, r):
            h = height(x + ox, y + oy)
            if h is None or abs(h - cur_h) > MAX_STEP:
                return False
    return True


def _worst(x, y, cur_h):
    r, w = ROBOT / 2, 0.0
    for ox in (-r, 0, r):
        for oy in (-r, 0, r):
            h = height(x + ox, y + oy)
            if h is None:
                return None
            w = max(w, abs(h - cur_h))
    return w


def can_move(nx, ny, cur_h, ox, oy):
    """Seperti can_stand, tapi boleh mundur jika posisi sekarang sudah mepet (tidak lebih buruk)."""
    if solid(nx, ny):
        return False
    new = _worst(nx, ny, cur_h)
    if new is None:
        return False
    if new <= MAX_STEP:
        return True
    old = _worst(ox, oy, cur_h)
    return old is not None and new <= old + 1e-9


def zone_name(x, y):
    if abs(x) <= L2_HALF and abs(y) <= L2_HALF:
        return "L2"
    if L2_HALF < abs(x) <= L2_HALF + 0.6 and -0.6 <= y <= 0.7:
        return "Step L2"
    if abs(x) <= L1_HALF and abs(y) <= L1_HALF:
        return "L1"
    if BAND_X[0] < abs(x) <= BAND_X[1]:
        if BAND_Y[0] <= y <= BAND_Y[1]:
            return "Pad transfer"
        if RAMP_Y[0] < y <= RAMP_Y[1]:
            return "Ramp"
        if STAIR_Y[0] <= y < BAND_Y[0]:
            return "Tangga"
    return "Tanah"


# ═════════════════════ Navigasi grid A* ═════════════════════
CELL = 0.25
N = int(2 * 5.5 / CELL) + 1


def cxy(i):
    return -5.5 + CELL * i


HG = [[height(cxy(i), cxy(j)) for j in range(N)] for i in range(N)]
SOL = [[solid(cxy(i), cxy(j)) for j in range(N)] for i in range(N)]


def cell_ok(i, j, hcur):
    if not (0 <= i < N and 0 <= j < N) or SOL[i][j]:
        return False
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            a, b = i + di, j + dj
            if not (0 <= a < N and 0 <= b < N):
                return False
            h = HG[a][b]
            if h is None or abs(h - hcur) > MAX_STEP:
                return False
    return True


def nearest(x, y):
    return (min(N - 1, max(0, round((x + 5.5) / CELL))),
            min(N - 1, max(0, round((y + 5.5) / CELL))))


def plan_path(start, goal, avoid=None):
    si, sj = nearest(*start)
    gi, gj = nearest(*goal)
    if not cell_ok(gi, gj, HG[gi][gj]):
        return None
    heap, came, g, cnt = [(0, 0, (si, sj))], {}, {(si, sj): 0.0}, 0
    while heap:
        _, _, cur = heapq.heappop(heap)
        if cur == (gi, gj):
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return [(cxy(i), cxy(j)) for i, j in path[::-1]]
        i, j = cur
        hc = HG[i][j]
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di == 0 and dj == 0:
                    continue
                ni, nj = i + di, j + dj
                if not cell_ok(ni, nj, hc):
                    continue
                if di and dj and not (cell_ok(i + di, j, hc) and cell_ok(i, j + dj, hc)):
                    continue
                if avoid and (ni, nj) != (gi, gj) and avoid(cxy(ni), cxy(nj)):
                    continue
                ng = g[cur] + (1.414 if di and dj else 1.0)
                if ng < g.get((ni, nj), 1e9):
                    g[(ni, nj)], came[(ni, nj)] = ng, cur
                    cnt += 1
                    heapq.heappush(heap, (ng + math.hypot(ni - gi, nj - gj), cnt, (ni, nj)))
    return None


# ═════════════════════════ Model ═════════════════════════
class Robot:
    def __init__(self, x, y, team, role):
        self.x, self.y, self.team, self.role = x, y, team, role
        self.h = height(x, y)
        self.blocks, self.mustika = [], False
        self.heading = (0, 1) if x < 0 else (0, 1)
        self.state, self.status = "plan", "siap"
        self.busy = self.wait_t = self.wait_total = self.block_t = 0.0
        self.path, self.target, self.on_arrive = None, None, None
        self.speed = 1.0


class Team:
    def __init__(self, name, s, key):
        self.name, self.s, self.strategy = name, s, key
        self.strat, self.order = STRATEGIES[key], resolve_order(key, name)
        self.tr = Robot(s * 4.75, -5.05, name, "TR")
        self.br = Robot(s * 3.25, -5.05, name, "BR")
        self.src, self.stock = dict(STOCK0), {"E": 0, "S": 0}
        self.transfer, self.trans_stand = (s * 3.5, -0.4), (s * 3.5, -0.6)
        self.trans_work = (s * 2.5, -0.5)
        self.earth, self.sky = (s * 4.9, 2.2), (s * 0.5, -4.45)
        self.pillar_work = (0.0, s * 0.75)
        self.flip_ai, self.flip_cd, self.flip_cd_manual, self.tr_flip_cd = False, 0.0, 0.0, 0.0
        if name == "blue":
            self.tr.speed = self.br.speed = ENEMY_SPEED


class Game:
    """Logika permainan (tanpa GUI) — bisa dites tanpa Tkinter."""

    def __init__(self):
        self.mode = "manual"                              # manual | auto
        self.sel = {"red": "RUSH", "blue": "DISRUPT"}     # strategi tiap tim
        self.br_manual, self.enemy_on, self.active = False, True, "TR"
        self.reset()

    def reset(self):
        self.time_left = MATCH_TIME
        self.red, self.blue = Team("red", -1, self.sel["red"]), Team("blue", 1, self.sel["blue"])
        if self.mode != "manual":                         # bot vs bot: kecepatan sama
            self.blue.tr.speed = self.blue.br.speed = 1.0
        self.red.flip_ai = self.blue.flip_ai = True
        self.active = "TR"
        self.fx = {}
        self.teams = {"red": self.red, "blue": self.blue}
        self.robots = [self.red.tr, self.red.br, self.blue.tr, self.blue.br]
        self.levels = {k: [] for k in SPOTS}     # tiap blok: [tipe, pemilik]
        self.m_state, self.m_owner = "pedestal", None    # pedestal | held | placed
        self.over = self.paused = False
        self.started, self.countdown = False, 0.0
        self.log = deque(maxlen=9)
        self.msg = ("Mode MANUAL: gerakkan TR dengan panah / WASD." if self.mode == "manual"
                    else "Mode AUTO: bot vs bot, tekan START.")
        self.say("Siap — tekan START (Enter).")

    @property
    def live(self):
        return self.started and self.countdown <= 0 and not self.paused and not self.over

    def active_robot(self):
        return self.red.br if (self.br_manual and self.active == "BR") else self.red.tr

    def set_br_manual(self, v):
        v = bool(v) and self.mode == "manual"
        if v == self.br_manual:
            return
        self.br_manual = v
        if v:
            self.msg = "BR merah MANUAL — TAB ganti TR/BR"
        else:
            self.active = "TR"
            b = self.red.br                      # kembalikan ke kendali AI
            b.state, b.path, b.busy, b.on_arrive = "plan", None, 0.0, None
            self.msg = "BR merah kembali AUTO"

    def switch_active(self):
        if self.mode == "manual" and self.br_manual:
            self.active = "BR" if self.active == "TR" else "TR"
            self.msg = f"Kontrol: {self.active} merah"
        else:
            self.msg = "TAB aktif jika 'BR merah manual' dicentang (atau tekan B)"

    def start(self):
        if self.started:
            return
        self.started, self.countdown = True, COUNTDOWN
        self.msg = "Bersiap..." if COUNTDOWN > 0 else "GO!"
        if COUNTDOWN <= 0:
            self.say("Match dimulai!")

    def toggle_pause(self):
        if self.started and not self.over and self.countdown <= 0:
            self.paused = not self.paused

    def say(self, t):
        self.log.append(f"{MATCH_TIME - self.time_left:5.1f}s {t}")

    # ── skor & syarat ──
    def score(self, name):
        s = 0
        for k, lv in self.levels.items():
            for i, (_, own) in enumerate(lv):
                if own == name:
                    s += LEVEL_PTS[i] * SPOTS[k]["mult"]
        if self.m_state == "placed" and self.m_owner == name:
            s += MUSTIKA_PTS
        return s

    def has_tower(self, name, kind):
        return any(SPOTS[k]["kind"] == kind and len(lv) == 3 and lv[2][1] == name
                   for k, lv in self.levels.items())

    def ready(self, name):
        return self.has_tower(name, "L1") and self.has_tower(name, "L2")

    # ── util gerak ──
    def hit_other(self, me, nx, ny):
        for o in self.robots:
            if o is me:
                continue
            def ov(x, y):
                return abs(x - o.x) < ROBOT and abs(y - o.y) < ROBOT
            if ov(nx, ny):
                if not ov(me.x, me.y) or math.hypot(nx - o.x, ny - o.y) < math.hypot(me.x - o.x, me.y - o.y):
                    return True
        return False

    def move(self, r, dx, dy):
        for ddx, ddy in ((dx, dy), (dx, 0), (0, dy)):
            if ddx == 0 and ddy == 0:
                continue
            nx, ny = r.x + ddx, r.y + ddy
            if can_move(nx, ny, r.h, r.x, r.y) and not self.hit_other(r, nx, ny):
                r.x, r.y, r.h = nx, ny, height(nx, ny)
                return True
        return False

    @staticmethod
    def dist(r, p):
        return math.hypot(r.x - p[0], r.y - p[1])

    # ── aksi dasar (dipakai TR manual & AI) ──
    def pick(self, t, r, typ):
        if len(r.blocks) >= 3:
            return "Robot penuh (maks 3 blok)"
        if t.src[typ] <= 0:
            return "Stok habis"
        t.src[typ] -= 1
        r.blocks.append(typ)
        return f"Ambil {typ} ({len(r.blocks)}/3)"

    def deposit(self, t, r):
        moved = []
        for b in r.blocks[:]:
            if t.stock[b] < CAP[b]:
                t.stock[b] += 1
                r.blocks.remove(b)
                moved.append(b)
        if moved:
            self.say(f"{t.name[0].upper()}-TR: taruh {''.join(moved)} ke Transfer")
        return f"Diletakkan: {' '.join(moved)}" if moved else "Transfer penuh untuk blok itu"

    def flip(self, t, r, sp):
        lv = self.levels[sp]
        old = lv[-1][1]
        lv[-1][1] = t.name
        self.fx[sp] = 1.0
        self.say(f"{t.name[0].upper()}-{r.role}: BALIK blok atas {sp} ({old} -> {t.name})")

    def flip_candidates(self, t, strict=False):
        """Menara dengan blok atas milik lawan.
        strict=True (aturan BR): hanya spot TENGAH yang sudah tertumpuk 3 kotak."""
        out = []
        for k, lv in self.levels.items():
            if not lv or lv[-1][1] == t.name:
                continue
            if strict and not (k in MIDDLE_SPOTS and len(lv) == 3):
                continue
            out.append(k)
        return out

    # ── TR manual (merah) ──
    def tr_interact(self):
        t, r = self.red, self.red.tr
        if not self.live:
            self.msg = "Tekan START dulu" if not self.started else self.msg
            return
        if r.blocks and self.dist(r, t.transfer) <= REACH_TRANSFER:
            self.msg = self.deposit(t, r)
        elif self.dist(r, t.earth) <= 1.4:
            self.msg = self.pick(t, r, "E")
        elif self.dist(r, SKY_CENTER) <= REACH_SRC:
            self.msg = self.pick(t, r, "S")
        else:
            self.msg = "Tidak ada objek dalam jangkauan (gudang / Transfer)"

    def interact(self):
        if self.mode != "manual":
            return
        if self.active_robot().role == "BR":
            return self.br_interact()
        return self.tr_interact()

    def br_interact(self):
        t, r = self.red, self.red.br
        if not self.live:
            self.msg = "Tekan START dulu" if not self.started else self.msg
            return

        def d(p):
            return math.hypot(r.x - p[0], r.y - p[1])
        if r.mustika and d((0.0, 0.0)) <= 1.1:
            self.place_mustika(t)
            self.msg = "Mustika diletakkan di tiang tengah! +250"
            return
        if not r.mustika and not r.blocks and self.m_state == "pedestal" and d(MUSTIKA_POS) <= REACH_PED:
            if not self.ready("red"):
                self.msg = "Belum boleh: butuh menara selesai di L1 DAN L2 (blok atas milik merah)"
            else:
                self.take_mustika(t)
                self.msg = "Mustika diambil! Bawa ke tiang tengah (L2)."
            return
        if r.blocks:
            fit = [k for k, sd in SPOTS.items()
                   if len(self.levels[k]) < 3 and SEQ[len(self.levels[k])] == r.blocks[0]
                   and math.hypot(r.x - sd["pos"][0], r.y - sd["pos"][1]) <= REACH_FLIP]
            if fit:
                sp = min(fit, key=lambda k: math.hypot(r.x - SPOTS[k]["pos"][0], r.y - SPOTS[k]["pos"][1]))
                self.place(t, sp)
                r.busy = 0.0
                self.msg = f"Taruh blok di {sp} ({len(self.levels[sp])}/3)"
                return
        if d(t.transfer) <= REACH_TRANSFER:
            if len(r.blocks) >= 2:
                self.msg = "BR penuh (maks 2 blok)"
                return
            sp = self.next_spot(t)
            need = SEQ[len(self.levels[sp]):] if sp else []
            pref = need[len(r.blocks)] if len(r.blocks) < len(need) else "E"
            for typ in (pref, "S" if pref == "E" else "E"):
                if t.stock[typ] > 0:
                    t.stock[typ] -= 1
                    r.blocks.append(typ)
                    self.msg = f"Ambil {typ} dari Transfer ({len(r.blocks)}/2)"
                    return
            self.msg = "Transfer kosong"
            return
        self.msg = ("Tidak ada aksi di sini (dekati Transfer / menara / pedestal / tiang tengah)"
                    if not r.blocks else "Blok tidak cocok urutan menara (E, E, S) / terlalu jauh dari menara")

    def tr_flip(self):
        t, r = self.red, self.active_robot()
        if not self.live or self.mode != "manual":
            return
        if t.flip_cd_manual > 0:
            self.msg = f"Balik: cooldown {t.flip_cd_manual:.1f}s"
            return
        cands = [k for k in self.flip_candidates(t, strict=(r.role == "BR" or not FLIP_TR_ANYWHERE))
                 if math.hypot(r.x - SPOTS[k]["pos"][0], r.y - SPOTS[k]["pos"][1]) <= REACH_FLIP]
        if not cands:
            self.msg = "Tidak ada kotak lawan dalam jangkauan (1.3 m)"
            return
        sp = min(cands, key=lambda k: math.hypot(r.x - SPOTS[k]["pos"][0], r.y - SPOTS[k]["pos"][1]))
        self.flip(t, r, sp)
        t.flip_cd_manual = 1.0
        self.msg = f"Kotak lawan di {sp} dibalik!"

    # ── navigasi AI ──
    def go(self, r, target, cb, text):
        r.target, r.on_arrive, r.path, r.state, r.status = target, cb, None, "move", text

    def follow(self, r, dt):
        if r.path is None:
            def avoid(x, y):
                return any(o is not r and abs(x - o.x) < 0.65 and abs(y - o.y) < 0.65
                           for o in self.robots)
            p = plan_path((r.x, r.y), r.target, avoid) or plan_path((r.x, r.y), r.target)
            if p is None:
                r.state, r.busy, r.status = "plan", 1.0, "tidak ada jalur"
                return
            r.path = p[1:]
        if not r.path:
            if math.hypot(r.x - r.target[0], r.y - r.target[1]) < 0.2:
                r.state = "plan"
                cb, r.on_arrive = r.on_arrive, None
                return cb() if cb else None
            r.path = [r.target]
        tx, ty = r.path[0]
        d = math.hypot(tx - r.x, ty - r.y)
        step = BR_SPEED * r.speed * dt
        nx, ny = (tx, ty) if d <= step else (r.x + (tx - r.x) / d * step, r.y + (ty - r.y) / d * step)
        if can_move(nx, ny, r.h, r.x, r.y) and not self.hit_other(r, nx, ny):
            if d > 1e-6:
                r.heading = ((tx - r.x) / d, (ty - r.y) / d)
            r.x, r.y, r.h, r.block_t = nx, ny, height(nx, ny), 0.0
            if d <= step:
                r.path.pop(0)
        else:
            r.block_t += dt
            if r.block_t > 0.6:
                r.path, r.block_t = None, 0.0

    def ai_tick(self, r, dt, planner):
        if r.busy > 0:
            r.busy -= dt
        elif r.state == "move":
            self.follow(r, dt)
        elif r.state == "wait":
            r.wait_t += dt
            if r.wait_t >= 0.5:
                r.wait_total += 0.5
                r.state = "plan"
        else:
            planner()

    # ── BR builder (merah & biru) ──
    def next_spot(self, t):
        for k in t.order:
            if len(self.levels[k]) < 3:
                return k
        return None

    def spot_for(self, t, blk):
        for k in t.order:
            lv = self.levels[k]
            if len(lv) < 3 and SEQ[len(lv)] == blk:
                return k
        return None

    def builder_plan(self, t):
        r = t.br
        c = t.name[0].upper()
        if r.blocks:
            sp = self.spot_for(t, r.blocks[0])
            if sp:
                return self.go(r, SPOTS[sp]["work"], lambda: self.place(t, sp),
                               f"bawa {''.join(r.blocks)} -> {sp}")
            for b in r.blocks:                         # tak ada tempat cocok: kembalikan
                t.stock[b] = min(CAP[b], t.stock[b] + 1)
            r.blocks, r.busy = [], 0.5
            self.say(f"{c}-BR: blok tak cocok, dikembalikan")
            return
        if r.mustika:
            return self.go(r, t.pillar_work, lambda: self.place_mustika(t), "bawa Mustika -> tiang tengah")
        st = t.strat
        if self.m_state == "pedestal" and self.ready(t.name) and self.mustika_go(t):
            return self.go(r, PED_WORK, lambda: self.take_mustika(t), "L1+L2 siap -> ambil Mustika!")
        if t.flip_ai and t.flip_cd <= 0 and MATCH_TIME - self.time_left >= st["flip_start"]:
            cands = self.flip_candidates(t, strict=True)
            if cands:
                sp = cands[0]
                return self.go(r, SPOTS[sp]["work"], lambda: self.br_flip(t, sp),
                               f"balik kotak atas {sp}")
        sp = self.next_spot(t)
        if sp is None:
            r.status, r.busy = "semua menara selesai", 1.0
            return
        if self.dist(r, t.trans_work) < 0.3:
            return self.try_take(t, sp)
        self.go(r, t.trans_work, lambda: self.try_take(t, self.next_spot(t)), "ke Transfer")

    def mustika_go(self, t):
        """Kebijakan Mustika per strategi: asap = begitu siap; snipe = tunggu akhir match / lawan siap."""
        if t.strat["mustika"] == "asap":
            return True
        opp = "blue" if t.name == "red" else "red"
        return self.time_left <= SNIPE_AT or self.ready(opp)

    def try_take(self, t, sp):
        r = t.br
        if sp is None:
            return
        seq = SEQ[len(self.levels[sp]):][:2]
        take, tmp = [], dict(t.stock)
        for typ in seq:
            if tmp[typ] > 0:
                take.append(typ)
                tmp[typ] -= 1
            else:
                break
        if take and (len(take) == len(seq) or r.wait_total > 6):
            for typ in take:
                t.stock[typ] -= 1
                r.blocks.append(typ)
            r.busy, r.wait_total, r.state = 0.4 * len(take), 0.0, "plan"
            r.status = f"ambil {''.join(take)}"
            self.say(f"{t.name[0].upper()}-BR: ambil {''.join(take)} dari Transfer")
        else:
            r.state, r.wait_t, r.status = "wait", 0.0, f"menunggu stok ({''.join(seq)})"

    def place(self, t, sp):
        r, lv = t.br, self.levels[sp]
        placed = []
        while r.blocks and len(lv) < 3 and SEQ[len(lv)] == r.blocks[0]:
            blk = r.blocks.pop(0)
            lv.append([blk, t.name])
            placed.append(blk)
        r.busy, r.state, r.status = 0.5 * max(1, len(placed)), "plan", "menempatkan blok"
        if placed:
            self.say(f"{t.name[0].upper()}-BR: taruh {''.join(placed)} di {sp} ({len(lv)}/3)")
            if len(lv) == 3 and lv[2][1] == t.name and self.ready(t.name) and self.m_state == "pedestal":
                self.say(f"{t.name[0].upper()}: menara L1+L2 siap -> BR kejar Mustika!")

    def take_mustika(self, t):
        r = t.br
        if self.m_state == "pedestal":
            r.mustika, self.m_state, self.m_owner = True, "held", t.name
            r.busy, r.status = 0.6, "ambil Mustika"
            self.say(f"{t.name[0].upper()}-BR: AMBIL MUSTIKA langsung dari pedestal")
        r.state = "plan"

    def place_mustika(self, t):
        r = t.br
        r.mustika, self.m_state, self.m_owner = False, "placed", t.name
        r.busy, r.state, r.status = 0.8, "plan", "Mustika ditaruh!"
        self.say(f"{t.name[0].upper()}-BR: MUSTIKA diletakkan! +{MUSTIKA_PTS}")

    def br_flip(self, t, sp):
        r, lv = t.br, self.levels[sp]
        if sp in MIDDLE_SPOTS and len(lv) == 3 and lv[-1][1] != t.name:
            self.flip(t, r, sp)
            r.busy, t.flip_cd = 0.8, t.strat["flip_cd"]
        r.state = "plan"

    # ── feeder AI (TR biru) ──
    def feeder_plan(self, t):
        r = t.tr
        if r.blocks:
            return self.go(r, t.trans_stand, lambda: self.feeder_deposit(t), "antar blok -> Transfer")
        st = t.strat
        if st["tr_flip"] and t.tr_flip_cd <= 0 and MATCH_TIME - self.time_left >= st["tr_flip_start"]:
            opp = "blue" if t.name == "red" else "red"
            cands = [k for k in self.flip_candidates(t) if len(self.levels[k]) == 3]

            def prio(k):                     # menara tunggal penentu syarat Mustika lawan = prioritas
                kind = SPOTS[k]["kind"]
                n = sum(1 for kk, lv in self.levels.items()
                        if SPOTS[kk]["kind"] == kind and len(lv) == 3 and lv[2][1] == opp)
                return 0 if (n == 1 and self.m_state == "pedestal") else 1
            if cands:
                sp = sorted(cands, key=prio)[0]
                return self.go(r, SPOTS[sp]["work"], lambda: self.tr_ai_flip(t, sp), f"ganggu: balik {sp}")
        want = ["E", "E", "S"] if (t.stock["S"] < 1 and t.src["S"] > 0) else ["E", "E", "E"]
        nE = min(want.count("E"), t.src["E"], CAP["E"] - t.stock["E"])
        nS = min(want.count("S"), t.src["S"], CAP["S"] - t.stock["S"])
        if nE + nS == 0:
            r.status, r.busy = "menunggu ruang Transfer", 1.0
            return

        def at_sky():
            for _ in range(nS):
                self.pick(t, r, "S")
            r.busy = 0.3 * nS

        def at_earth():
            for _ in range(nE):
                self.pick(t, r, "E")
            r.busy = 0.3 * nE
            if nS:
                self.go(r, t.sky, at_sky, "ambil Sky")

        if nE:
            self.go(r, t.earth, at_earth, "ambil Earth")
        else:
            self.go(r, t.sky, at_sky, "ambil Sky")

    def tr_ai_flip(self, t, sp):
        r, lv = t.tr, self.levels[sp]
        if len(lv) == 3 and lv[-1][1] != t.name:
            self.flip(t, r, sp)
            r.busy, t.tr_flip_cd = 0.8, t.strat["tr_flip_cd"]
        r.state = "plan"

    def feeder_deposit(self, t):
        self.deposit(t, t.tr)
        t.tr.busy = 0.4

    # ── step utama ──
    def step(self, dt, vx=0.0, vy=0.0):
        if self.over or self.paused or not self.started:
            return
        if self.countdown > 0:
            self.countdown -= dt
            if self.countdown <= 0:
                self.countdown = 0.0
                self.msg = "GO!"
                self.say("Match dimulai! GO!")
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left, self.over = 0.0, True
            a, b = self.score("red"), self.score("blue")
            self.say(f"WAKTU HABIS. Merah {a} - Biru {b}")
            return
        for k in list(self.fx):
            self.fx[k] -= dt
            if self.fx[k] <= 0:
                del self.fx[k]
        for t in self.teams.values():
            t.flip_cd = max(0.0, t.flip_cd - dt)
            t.flip_cd_manual = max(0.0, t.flip_cd_manual - dt)
            t.tr_flip_cd = max(0.0, t.tr_flip_cd - dt)
        if self.mode == "manual":
            r = self.active_robot()
            if vx or vy:
                n = math.hypot(vx, vy)
                r.heading = (vx / n, vy / n)
                if not self.move(r, vx / n * TR_SPEED * dt, vy / n * TR_SPEED * dt):
                    self.msg = "Terhalang (dinding / beda tinggi > 0.25 m / robot)"
            if not self.br_manual:
                self.ai_tick(self.red.br, dt, lambda: self.builder_plan(self.red))
        else:                                              # AUTO: semua robot merah juga AI
            self.ai_tick(self.red.br, dt, lambda: self.builder_plan(self.red))
            self.ai_tick(self.red.tr, dt, lambda: self.feeder_plan(self.red))
        if self.enemy_on:
            self.ai_tick(self.blue.br, dt, lambda: self.builder_plan(self.blue))
            self.ai_tick(self.blue.tr, dt, lambda: self.feeder_plan(self.blue))


# ═════════════════════════ GUI ═════════════════════════
S, M = 58, 22
W = int(2 * HALF * S) + 2 * M
PROF_H = 100
BG = "#0d1117"
KEYV = {"up": (0, 1), "w": (0, 1), "down": (0, -1), "s": (0, -1),
        "left": (-1, 0), "a": (-1, 0), "right": (1, 0), "d": (1, 0)}
EC, SC = "#a0522d", "#7ec8e3"
TEAM_COL = {"red": "#ff3b3b", "blue": "#3b6bff"}
ROBOT_COL = {("red", "TR"): "#ff3b3b", ("red", "BR"): "#e07b00",
             ("blue", "TR"): "#3b6bff", ("blue", "BR"): "#00a8c8"}


def spans(side, ax, bx, y0, y1):
    xa, xb = sorted((side * ax, side * bx))
    return xa, y0, xb, y1


class App:
    def __init__(self, root):
        self.root = root
        root.title("ABU Robocon 2027 — Mode MANUAL / AUTO")
        root.configure(bg=BG)
        self.g = Game()
        self.keys, self.rel, self.space = set(), {}, False
        self.labels = True
        self.last = time.time()

        tk.Label(root, text="ABU ROBOCON 2027 — THE PURSUIT OF MUSTIKA NUSANTARA",
                 bg=BG, fg="#4ade80", font=("Courier", 12, "bold")).pack(pady=(6, 2))
        cfg = tk.Frame(root, bg=BG)
        cfg.pack(pady=(0, 4))
        self.cfg_widgets, self.cfg_state = [], None
        lab = dict(bg=BG, fg="#94a3b8", font=("Courier", 9, "bold"))
        tk.Label(cfg, text="MODE:", **lab).pack(side="left")
        self.mode_var = tk.StringVar(value=self.g.mode)
        for txt, val in (("MANUAL (main sendiri)", "manual"), ("AUTO (bot vs bot)", "auto")):
            rb = tk.Radiobutton(cfg, text=txt, value=val, variable=self.mode_var, command=self.on_cfg,
                                indicatoron=0, bg="#1f2937", fg="white", selectcolor="#2563eb",
                                activebackground="#374151", activeforeground="white",
                                font=("Courier", 9, "bold"), relief="flat", padx=8, pady=2, takefocus=0)
            rb.pack(side="left", padx=2)
            self.cfg_widgets.append(rb)

        def strat_menu(label, var):
            tk.Label(cfg, text=label, **lab).pack(side="left")
            om = tk.OptionMenu(cfg, var, *STRATEGIES, command=lambda _v: self.on_cfg())
            om.config(bg="#1f2937", fg="white", activebackground="#374151", activeforeground="white",
                      font=("Courier", 9, "bold"), highlightthickness=0, takefocus=0, width=9)
            om["menu"].config(font=("Courier", 9))
            om.pack(side="left", padx=2)
            self.cfg_widgets.append(om)
        self.sr_var = tk.StringVar(value=self.g.sel["red"])
        self.sb_var = tk.StringVar(value=self.g.sel["blue"])
        strat_menu("  Strategi MERAH:", self.sr_var)
        strat_menu(" BIRU:", self.sb_var)
        self.brm_var = tk.BooleanVar(value=self.g.br_manual)
        self.brm_cb = tk.Checkbutton(cfg, text="BR merah manual (Tab)", variable=self.brm_var,
                                     command=self.on_brm, bg=BG, fg="#cbd5e1", selectcolor="#111827",
                                     activebackground=BG, activeforeground="white",
                                     font=("Courier", 9), takefocus=0)
        self.brm_cb.pack(side="left", padx=(8, 0))
        bar = tk.Frame(root, bg=BG)
        bar.pack(pady=(0, 4))
        self.btn_main = tk.Button(bar, text="▶  START", width=14, command=self.main_action,
                                  bg="#16a34a", fg="white", activebackground="#22c55e",
                                  font=("Courier", 11, "bold"), relief="flat", takefocus=0)
        self.btn_main.pack(side="left", padx=4)
        self.btn_reset = tk.Button(bar, text="↺  RESET", width=10, command=self.on_reset,
                                   bg="#374151", fg="white", activebackground="#4b5563",
                                   font=("Courier", 11, "bold"), relief="flat", takefocus=0)
        self.btn_reset.pack(side="left", padx=4)
        self.btn_txt = None
        body = tk.Frame(root, bg=BG)
        body.pack(padx=8)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left")
        self.cv = tk.Canvas(left, width=W, height=W, bg="#c9c9c4", highlightthickness=0)
        self.cv.pack()
        self.prof = tk.Canvas(left, width=W, height=PROF_H, bg="#10161d", highlightthickness=0)
        self.prof.pack(pady=(4, 0))
        self.panel = tk.Label(body, bg="#0f1923", fg="#e2e8f0", font=("Courier", 9),
                              justify="left", anchor="nw", width=52, wraplength=470, padx=8, pady=6)
        self.panel.pack(side="left", fill="y", padx=(8, 0))
        self.info = tk.Label(root, bg="#0f1923", fg="#e2e8f0", font=("Courier", 10), anchor="w")
        self.info.pack(fill="x", padx=8, pady=4)
        tk.Label(root, text="Enter=START • MANUAL: panah/WASD • SPASI aksi • F balik • TAB ganti TR/BR • B BR manual • "
                            "G BR balik-auto • E musuh • P pause • R reset • H label",
                 bg=BG, fg="#64748b", font=("Courier", 8)).pack(pady=(0, 6))

        root.bind("<KeyPress>", self.on_press)
        root.bind("<KeyRelease>", self.on_release)
        self.cv.bind("<Button-1>", self.on_click)
        self.draw_static()
        self.tick()

    # ── konfigurasi mode / strategi ──
    def on_cfg(self):
        g = self.g
        if g.started and not g.over:                      # terkunci saat match berjalan
            self.mode_var.set(g.mode)
            self.sr_var.set(g.sel["red"])
            self.sb_var.set(g.sel["blue"])
            self.root.focus_set()
            return
        g.mode = self.mode_var.get()
        g.sel["red"], g.sel["blue"] = self.sr_var.get(), self.sb_var.get()
        g.br_manual = g.br_manual and g.mode == "manual"
        self.brm_var.set(g.br_manual)
        if not g.started:
            g.reset()
        self.root.focus_set()

    def on_brm(self):
        self.g.set_br_manual(self.brm_var.get())
        self.brm_var.set(self.g.br_manual)
        self.root.focus_set()

    # ── tombol ──
    def main_action(self):
        g = self.g
        if g.over:
            g.reset()
            g.start()
        elif not g.started:
            g.start()
        else:
            g.toggle_pause()
        self.root.focus_set()

    def on_reset(self):
        self.g.reset()
        self.root.focus_set()

    def refresh_buttons(self):
        g = self.g
        if g.over:
            txt, col, st = "▶  MAIN LAGI", "#16a34a", "normal"
        elif not g.started:
            txt, col, st = "▶  START", "#16a34a", "normal"
        elif g.countdown > 0:
            txt, col, st = "…  BERSIAP", "#6b7280", "disabled"
        elif g.paused:
            txt, col, st = "▶  LANJUT", "#16a34a", "normal"
        else:
            txt, col, st = "⏸  PAUSE", "#d97706", "normal"
        if (txt, st) != self.btn_txt:
            self.btn_txt = (txt, st)
            self.btn_main.config(text=txt, bg=col, state=st)
        locked = g.started and not g.over
        key = (locked, g.mode)
        if key != self.cfg_state:
            self.cfg_state = key
            for w in self.cfg_widgets:
                w.config(state="disabled" if locked else "normal")
            self.brm_cb.config(state="normal" if g.mode == "manual" else "disabled")
        if self.brm_var.get() != g.br_manual:
            self.brm_var.set(g.br_manual)

    # ── input ──
    def on_press(self, e):
        k = e.keysym.lower()
        if k in self.rel:
            self.root.after_cancel(self.rel.pop(k))
        g = self.g
        if k == "tab":
            g.switch_active()
            return "break"
        if k in KEYV:
            if g.mode == "manual":
                self.keys.add(k)
        elif k == "space":
            if not self.space:
                self.space = True
                g.interact()
        elif k == "f":
            g.tr_flip()
        elif k == "return":
            if not g.started:
                g.start()
            elif g.over:
                g.reset()
                g.start()
        elif k == "p":
            g.toggle_pause()
        elif k == "b":
            if g.mode == "manual":
                g.set_br_manual(not g.br_manual)
            else:
                g.msg = "Mode AUTO: semua robot dikendalikan bot"
        elif k == "g":
            g.red.flip_ai = not g.red.flip_ai
            g.msg = f"BR merah auto-balik (tengah 3 tumpuk): {'ON' if g.red.flip_ai else 'OFF'}"
        elif k == "e":
            g.enemy_on = not g.enemy_on
            g.msg = f"Musuh: {'ON' if g.enemy_on else 'OFF'}"
        elif k == "r":
            g.reset()
        elif k == "h":
            self.labels = not self.labels
            self.draw_static()

    def on_release(self, e):
        k = e.keysym.lower()

        def rel():
            self.keys.discard(k)
            if k == "space":
                self.space = False
            self.rel.pop(k, None)
        if k in self.rel:
            self.root.after_cancel(self.rel[k])
        self.rel[k] = self.root.after(45, rel)

    def on_click(self, e):
        x, y = (e.x - M) / S - HALF, HALF - (e.y - M) / S
        if self.g.mode != "manual":
            return
        h, tr = height(x, y), self.g.active_robot()
        if h is not None and can_stand(x, y, h) and not self.g.hit_other(tr, x, y):
            tr.x, tr.y, tr.h = x, y, h
            self.g.msg = "teleport"
        else:
            self.g.msg = "Posisi tidak valid"

    def tick(self):
        now = time.time()
        dt = min(now - self.last, 0.1)
        self.last = now
        vx = sum(KEYV[k][0] for k in self.keys)
        vy = sum(KEYV[k][1] for k in self.keys)
        self.g.step(dt, vx, vy)
        self.draw_dynamic()
        self.root.after(40, self.tick)

    # ── primitif ──
    @staticmethod
    def px(x):
        return M + (x + HALF) * S

    @staticmethod
    def py(y):
        return M + (HALF - y) * S

    def rect(self, x0, y0, x1, y1, fill, outline="", width=1, shadow=False, **kw):
        a, b, c, d = self.px(x0), self.py(y1), self.px(x1), self.py(y0)
        if shadow:
            self.cv.create_rectangle(a + 5, b + 5, c + 5, d + 5, fill="black",
                                     stipple="gray50", outline="", **kw)
        return self.cv.create_rectangle(a, b, c, d, fill=fill, outline=outline, width=width, **kw)

    def label(self, x, y, text, fill="#222", size=8, bold=False, **kw):
        if self.labels:
            self.cv.create_text(self.px(x), self.py(y), text=text, fill=fill,
                                font=("Courier", size, "bold" if bold else "normal"), **kw)

    # ── peta statis ──
    def draw_static(self):
        cv = self.cv
        cv.delete("all")
        R, B, GRN = "#cc2222", "#2a00f0", "#2d6a2f"
        self.rect(-HALF, -HALF, 0, HALF, "#e8c8c4")
        self.rect(0, -HALF, HALF, HALF, "#75b3cc")
        for s, col in ((-1, R), (1, B)):
            self.rect(*spans(s, 2.5, 5.55, 4.6, 5.55), col)
            self.rect(*spans(s, 4.05, 5.55, -5.55, -4.55), col)
            self.rect(*spans(s, 2.5, 4.0, -5.55, -4.55), col)
            self.rect(*spans(s, 4.4, 5.4, 1.2, 3.2), "#c27c4a", "#6b3a1a", 2)     # gudang Earth
            self.label(s * 4.75, -5.3, "START TR", "#fff", 7, True)
            self.label(s * 3.25, -5.3, "START BR", "#fff", 7, True)
        gx0, gy0, g = -0.8, -5.25, 1.6
        self.rect(gx0 - 0.1, gy0 - 0.1, gx0 + g + 0.1, gy0 + g + 0.1, "#bdbdb5", "#777")
        for i in range(5):
            for j in range(5):
                col = "#8a5a1e" if (i, j) == (2, 2) else "#dfeccd"
                self.rect(gx0 + i * g / 5 + 0.02, gy0 + j * g / 5 + 0.02,
                          gx0 + (i + 1) * g / 5 - 0.02, gy0 + (j + 1) * g / 5 - 0.02, col)
        pal = {-1: ("#c98a84", "#e29b34", "#e2a79f"), 1: ("#6aa9bd", "#3a9ee0", "#8cc0d0")}
        for s in (-1, 1):
            rc, pc, sc = pal[s]
            x0, x1 = sorted((s * BAND_X[0], s * BAND_X[1]))
            self.rect(x0, RAMP_Y[0], x1, RAMP_Y[1], rc, "#555", 1, shadow=True)
            for k in range(1, 6):
                yy = RAMP_Y[0] + k * (RAMP_Y[1] - RAMP_Y[0]) / 6
                cv.create_line(self.px(x0), self.py(yy), self.px(x1), self.py(yy),
                               fill="#8a5f5a" if s < 0 else "#4b7f90")
            self.rect(x0, BAND_Y[0], x1, BAND_Y[1], pc, "#555", 1, shadow=True)
            self.rect(x0, STAIR_Y[0], x1, STAIR_Y[1], sc, "#555", 1, shadow=True)
            for k in (1, 2):
                yy = STAIR_Y[0] + k * (STAIR_Y[1] - STAIR_Y[0]) / 3
                cv.create_line(self.px(x0), self.py(yy), self.px(x1), self.py(yy), fill="#555", width=2)
            xm = (x0 + x1) / 2
            self.label(xm, 1.55, "RAMP", "#222", 8, True)
            self.label(xm, -1.95, "TANGGA", "#222", 8, True)
            self.label(xm, 0.3, "TRANSFER", "#222", 7, True)
        for sy in (1, -1):
            y0, y1 = sorted((sy * 2.5, sy * 3.5))
            self.rect(-0.75, y0, 0.75, y1, "#b5b2aa", "#555", 1, shadow=True)
        self.rect(-L1_HALF, -L1_HALF, 0, L1_HALF, "#e8ab96", "#555", 2, shadow=True)
        self.rect(0, -L1_HALF, L1_HALF, L1_HALF, "#78bfc3", "#555", 2)
        for sy in (1, -1):
            y0, y1 = sorted((sy * 2.5, sy * 3.5))
            self.rect(-0.75, y0, 0.75, y1, "#b5b2aa", "#555", 1)
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.rect(sx * 2.55 - 0.25, sy * 2.55 - 0.25, sx * 2.55 + 0.25, sy * 2.55 + 0.25, GRN)
        for sy in (-1, 1):
            self.rect(-0.25, sy * 3.0 - 0.25, 0.25, sy * 3.0 + 0.25, GRN)
        self.rect(-2.2, 2.4, -1.2, 3.0, R)
        self.rect(1.2, 2.4, 2.2, 3.0, B)
        for s in (-1, 1):
            x0, x1 = sorted((s * L2_HALF, s * (L2_HALF + 0.6)))
            self.rect(x0, -0.6, x1, 0.7, "#c5c1b9", "#555", 1, shadow=True)
        self.rect(-L2_HALF, -L2_HALF, L2_HALF, L2_HALF, "#b0aca4", "#444", 2, shadow=True)
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.rect(sx * 1.1 - 0.22, sy * 1.1 - 0.22, sx * 1.1 + 0.22, sy * 1.1 + 0.22, GRN)
        cv.create_oval(self.px(0) - 13, self.py(0) - 13, self.px(0) + 13, self.py(0) + 13,
                       fill="#8a5a1e", outline="#4a2e0a", width=2)
        for sy in (1, -1):                                   # zona TENGAH (BR bisa balik jika 3 tumpuk)
            y0, y1 = sorted((sy * 2.5, sy * 3.5))
            cv.create_rectangle(self.px(-0.75), self.py(y1), self.px(0.75), self.py(y0),
                                outline="#f59e0b", width=2, dash=(5, 3))
            self.label(1.35, sy * 3.0, "TENGAH", "#b45309", 7, True)
        for k, sd in SPOTS.items():
            x, y = sd["pos"]
            self.label(x, y - 0.45, k, "#222", 6)
        a, b, c, d = self.px(-HALF), self.py(HALF), self.px(HALF), self.py(-HALF)
        cv.create_rectangle(a, b, c, d, outline="#4a2e0a", width=6)

    # ── objek dinamis ──
    def draw_robot(self, r):
        cv, h = self.cv, ROBOT / 2
        col = ROBOT_COL[(r.team, r.role)]
        g = self.g
        if g.mode == "manual" and r is g.active_robot():
            cv.create_rectangle(self.px(r.x - h) - 5, self.py(r.y + h) - 5, self.px(r.x + h) + 5,
                                self.py(r.y - h) + 5, outline="#facc15", width=3, dash=(4, 3), tags="dyn")
        cv.create_rectangle(self.px(r.x - h), self.py(r.y + h), self.px(r.x + h), self.py(r.y - h),
                            fill=col, outline="white", width=2, tags="dyn")
        cv.create_line(self.px(r.x), self.py(r.y), self.px(r.x + r.heading[0] * h * 1.4),
                       self.py(r.y + r.heading[1] * h * 1.4), fill="white", width=3, arrow="last", tags="dyn")
        cv.create_text(self.px(r.x), self.py(r.y), text=r.role, fill="white",
                       font=("Courier", 9, "bold"), tags="dyn")
        items = [EC if b == "E" else SC for b in r.blocks] + (["#facc15"] if r.mustika else [])
        for i, c in enumerate(items):
            x0 = self.px(r.x) - len(items) * 5 + i * 10
            y0 = self.py(r.y + h) - 12
            cv.create_rectangle(x0, y0, x0 + 9, y0 + 9, fill=c, outline="black", tags="dyn")

    def draw_dynamic(self):
        g, cv = self.g, self.cv
        cv.delete("dyn")
        mx, my = MUSTIKA_POS
        self.rect(mx - 0.25, my - 0.25, mx + 0.25, my + 0.25, "#8a5a1e", "#4a2e0a", 2, tags="dyn")
        if g.m_state == "pedestal":
            cv.create_oval(self.px(mx) - 7, self.py(my) - 7, self.px(mx) + 7, self.py(my) + 7,
                           fill="#facc15", outline="", tags="dyn")
        self.label(mx, my + 0.55, "MUSTIKA", "#333", 7, True, tags="dyn")
        if g.m_state == "placed":
            cv.create_oval(self.px(0) - 9, self.py(0) - 9, self.px(0) + 9, self.py(0) + 9, fill="#facc15",
                           outline=TEAM_COL[g.m_owner], width=3, tags="dyn")
        else:
            cv.create_oval(self.px(0) - 6, self.py(0) - 6, self.px(0) + 6, self.py(0) + 6,
                           outline="#facc15", tags="dyn")
        for t in g.teams.values():
            s = t.s
            self.label(s * 4.9, 3.45, f"EARTH x{t.src['E']}", "#4a2a10", 8, True, tags="dyn")
            base = s * 3.5
            for k in range(CAP["E"]):
                self.rect(base - 0.38 + 0.3 * k, -0.27, base - 0.16 + 0.3 * k, -0.05,
                          EC if k < t.stock["E"] else "", "#333", 1, tags="dyn")
            for k in range(CAP["S"]):
                self.rect(base - 0.4 + 0.24 * k, -0.62, base - 0.22 + 0.24 * k, -0.42,
                          SC if k < t.stock["S"] else "", "#333", 1, tags="dyn")
        self.label(0, -3.62, f"SKY  M x{g.red.src['S']}   B x{g.blue.src['S']}", "#333", 8, True, tags="dyn")
        for k, sd in SPOTS.items():
            x, y = sd["pos"]
            lv = g.levels[k]
            for i, (b, own) in enumerate(lv):
                off = -i * 4
                cv.create_rectangle(self.px(x) - 10, self.py(y) - 10 + off, self.px(x) + 10,
                                    self.py(y) + 10 + off, fill=EC if b == "E" else SC,
                                    outline=TEAM_COL[own], width=3, tags="dyn")
            if lv:
                cv.create_text(self.px(x), self.py(y) - 4 * (len(lv) - 1), text=lv[-1][0],
                               font=("Courier", 8, "bold"), tags="dyn")
            if len(lv) == 3:
                cv.create_text(self.px(x), self.py(y) + 20, text="✓", fill="#b8860b",
                               font=("Courier", 10, "bold"), tags="dyn")
        for k, v in g.fx.items():
            x, y = SPOTS[k]["pos"]
            top = g.levels[k][-1][1] if g.levels[k] else "red"
            rad = 18 + (1 - v) * 26
            cv.create_oval(self.px(x) - rad, self.py(y) - rad, self.px(x) + rad, self.py(y) + rad,
                           outline=TEAM_COL[top], width=4, tags="dyn")
            cv.create_text(self.px(x), self.py(y) - rad - 8, text="BALIK!", fill=TEAM_COL[top],
                           font=("Courier", 9, "bold"), tags="dyn")
        for r in g.robots:
            self.draw_robot(r)
        if not g.started:
            cv.create_rectangle(W // 2 - 250, W // 2 - 70, W // 2 + 250, W // 2 + 70,
                                fill="#0d1117", outline="#4ade80", width=3, tags="dyn")
            cv.create_text(W // 2, W // 2 - 22, text="TEKAN  START  (Enter)", fill="#4ade80",
                           font=("Courier", 22, "bold"), tags="dyn")
            mm, ss = divmod(int(MATCH_TIME), 60)
            cv.create_text(W // 2, W // 2 + 22, text=f"Mode {g.mode.upper()}  •  durasi {mm:02d}:{ss:02d}",
                           fill="#94a3b8", font=("Courier", 10), tags="dyn")
        elif g.countdown > 0:
            cv.create_text(W // 2, W // 2, text=str(math.ceil(g.countdown)), fill="#fff",
                           font=("Courier", 90, "bold"), tags="dyn")
        elif g.paused or g.over:
            txt = "PAUSE" if not g.over else (
                f"SELESAI  M {g.score('red')} — B {g.score('blue')}")
            cv.create_text(W // 2, W // 2, text=txt, fill="#fff", font=("Courier", 24, "bold"), tags="dyn")
        self.draw_profile()
        self.update_text()
        self.refresh_buttons()

    def draw_profile(self):
        p, tr = self.prof, (self.g.active_robot() if self.g.mode == "manual" else self.g.red.tr)
        p.delete("all")
        base, sc = PROF_H - 18, 78
        pts = [(M, base)]
        for i in range(0, 2 * int(HALF * 20) + 1):
            x = -HALF + i / 20
            pts.append((self.px(x), base - (height(x, tr.y) or 0) * sc))
        pts.append((self.px(HALF), base))
        p.create_polygon([v for q in pts for v in q], fill="#34495e", outline="#7fb3d5")
        rx = self.px(tr.x)
        p.create_rectangle(rx - ROBOT / 2 * S, base - tr.h * sc - ROBOT * sc, rx + ROBOT / 2 * S,
                           base - tr.h * sc, fill="#ff3b3b", outline="white")
        p.create_text(M + 4, 4, anchor="nw", fill="#94a3b8", font=("Courier", 8),
                      text=f"Penampang tinggi di y = {tr.y:+.2f} m ({tr.role} merah)")

    def update_text(self):
        g = self.g
        m, s = divmod(int(g.time_left), 60)
        R, B = g.red, g.blue

        def carry(r):
            return (' '.join(r.blocks) or '-') + (' +Mustika' if r.mustika else '')
        rtr = "manual" if g.mode == "manual" else "AI"
        rbr = "manual" if (g.mode == "manual" and g.br_manual) else "AI"

        def mk(role):
            on = g.mode == "manual" and g.active_robot().role == role and (role == "TR" or g.br_manual)
            return " ◄" if on else ""
        ms = {"pedestal": "di pedestal", "held": f"dibawa BR {g.m_owner}",
              "placed": f"DITARUH oleh {g.m_owner}"}[g.m_state]
        lines = [f"WAKTU {m:02d}:{s:02d}",
                 f"MERAH {g.score('red'):4d}   |   BIRU {g.score('blue'):4d}   [{g.mode.upper()}]",
                 f"  M: {STRATEGIES[R.strategy]['label']} — {STRATEGIES[R.strategy]['desc']}",
                 f"  B: {STRATEGIES[B.strategy]['label']} — {STRATEGIES[B.strategy]['desc']}",
                 f"Mustika : {ms}",
                 f"Siap Mustika  M:{'✓' if g.ready('red') else '✗'}  B:{'✓' if g.ready('blue') else '✗'}"
                 "  (butuh menara L1+L2)",
                 "",
                 f"MERAH  TR {rtr}{mk('TR')}: " + (carry(R.tr) if rtr == "manual" else f"{R.tr.status} | {carry(R.tr)}"),
                 f"       BR {rbr}{mk('BR')}: " + (carry(R.br) if rbr == "manual" else f"{R.br.status} | {carry(R.br)}"),
                 f"BIRU   TR AI {'' if g.enemy_on else '(OFF)'}: {B.tr.status} | {carry(B.tr)}",
                 f"       BR AI {'' if g.enemy_on else '(OFF)'}: {B.br.status} | {carry(B.br)}",
                 f"TRANSFER M E{R.stock['E']}/{CAP['E']} S{R.stock['S']}/{CAP['S']}"
                 f"  B E{B.stock['E']}/{CAP['E']} S{B.stock['S']}/{CAP['S']}",
                 "MENARA (huruf kecil = pemilik: r/b)"]
        for k, v in g.levels.items():
            cell = "".join(f"{b}{own[0]}" for b, own in v)
            lines.append(f"  {k:8s} [{cell:<6s}] {'✓' if len(v) == 3 else ' '}"
                         f"{'  L2x2' if SPOTS[k]['mult'] == 2 else ''}")
        lines += ["", "TENGAH — BR balik jika 3 tumpuk & atas milik lawan"]
        for k in MIDDLE_SPOTS:
            lv = g.levels[k]
            cell = "".join(f"{b}{own[0]}" for b, own in lv)
            note = ""
            if len(lv) == 3:
                note = "← BR " + ("BIRU" if lv[2][1] == "red" else "MERAH") + " bisa balik"
            lines.append(f"  {k:8s} [{cell:<6s}] {len(lv)}/3 {note}")
        lines.append(f"  cooldown BR balik  M:{R.flip_cd:4.1f}s  B:{B.flip_cd:4.1f}s")
        lines += ["", "LOG"] + ["  " + t for t in g.log]
        self.panel.config(text="\n".join(lines))
        tr = g.active_robot() if g.mode == "manual" else R.tr
        cd = f" | balik siap" if R.flip_cd_manual <= 0 else f" | balik {R.flip_cd_manual:.1f}s"
        self.info.config(text=f" {tr.role} x={tr.x:+.2f} y={tr.y:+.2f} m | h={tr.h * 1000:4.0f} mm | "
                              f"{zone_name(tr.x, tr.y)}{cd} | {g.msg}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()