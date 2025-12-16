import pygame
import pygame.freetype
import math
import sys
import random
import json
import os
from collections import deque
import asyncio

try:
    import js
except Exception:  # desktop or older runtime
    js = None

# --- Setup ---
def resource_path(relative_path):
    """Works on dev, PyInstaller, and Pygbag (web)."""
    # Web (pygbag): use relative paths, not OS paths
    if sys.platform == "emscripten" or getattr(sys, "_emscripten_info", None):
        return relative_path
    # Desktop
    try:
        base_path = sys._MEIPASS  # set by PyInstaller
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

WEB = (sys.platform == "emscripten" or getattr(sys, "_emscripten_info", None))
print("WEB mode?", WEB)

# ---- JS bridge (safe on desktop & web) ----
try:
    if WEB:
        import js  # provided by pygbag in the browser
    else:
        js = None
except Exception:
    js = None

# no-op console so calls like js.console.log(...) never crash on desktop
class _NoopConsole:
    def log(self, *args, **kwargs): pass

class _NoJS:
    console = _NoopConsole()
    def __getattr__(self, name):
        # return a no-op callable for any attribute
        def _noop(*args, **kwargs): 
            return None
        return _noop

if js is None:
    js = _NoJS()
# ---- end JS bridge ----

HEXAGRAM_DATA = {}  # filled later in load_data()

BG_COLOR = (30, 30, 30)
WIDTH, HEIGHT = 1000, 750
screen = None  # filled in run_game()

# --- Web detection (put near imports)
WEB = (sys.platform == "emscripten" or getattr(sys, "_emscripten_info", None))

# --- Asset placeholders (filled later in load_assets) ---
HEXAGRAM_DATA = {}       # JSON loaded later
icon = None
ICON_SURF = None
font = None
TOOLTIP_FONT = None
chinese_font = None
symbol_font = None
hexagram_font = None

# constants that used to depend on font at import-time → safe defaults
GRID_ROW_GAP = 18      # was: max(18, font.get_height())
# (add similar safe defaults for any other font-based constants if you have them)

# --- UI Setup ---
coins_button_width = 180
coins_button_height = 40
coins_button_x = (WIDTH - coins_button_width) // 2
coins_button_y = HEIGHT - 160
coins_button = pygame.Rect(coins_button_x, coins_button_y, coins_button_width, coins_button_height)
deck_icon_size = 40
help_button = pygame.Rect(WIDTH - 50, coins_button_y, 40, 40)
help_button.right = 975
help_popup_visible = False
deck_icon_x = help_button.left - deck_icon_size - 10
deck_icon_rect = pygame.Rect(deck_icon_x, help_button.y, deck_icon_size, deck_icon_size)
DECK_POPUP_RECT = None
HELP_POPUP_RECT = None
HINT_GAP = 10

# Deck icon position
deck_icon_rect.right = help_button.left - HINT_GAP
deck_icon_rect.y = help_button.y

# Hint button position
hint_icon_size = deck_icon_size
hint_icon_rect = pygame.Rect(0, help_button.y, hint_icon_size, hint_icon_size)
hint_icon_rect.right = deck_icon_rect.left - HINT_GAP

# --- Hint usage counters ---
HINTS_COUNT_THIS_ROUND = 0   # increments each time the player buys a one-move hint
RUN_HINTS_COUNT        = 0   # cumulative across the run

OPTIMAL_BONUS_IP  = 1   # +1 if current_moves == ROUND_OPTIMAL_DIST (even with hints)
HINT_PENALTY_IP   = 1   # −1 per hint
AWARD_FLOOR_IP    = 0   # clamp final award at >= 0

# Transformation buttons
button_width = 102
button_height = 80
button_spacing = 8
button_start_x = 10
transform_button_y = HEIGHT - 110

# ── Shop knobs
BUY_START_COST = 6      # cost of the first purchase
BUY_COST_STEP  = 6      # cost increase after each purchase
SHOP_VISIBLE = False

# ── Persistent unlocks (per run)
# Start with 3 freebies: Shift, Invert lower, Mirror
FREEBIE_SHORTS = {"SHIFT", "INVERT ▼", "MIRROR ▲"}

# Current price for the next purchase this run
BUY_COST_CURRENT = BUY_START_COST

# Hexagram line styling
HEX_LINE_THICK     = 4     # vertical thickness of each line
HEX_INNER_PAD      = 15    # padding inside the card where lines live
HEX_YIN_GAP_RATIO  = 0.22  # % of inner width reserved for the yin center gap
HEX_LINE_RADIUS    = 2     # corner radius of each bar
HEX_LINE_COLOR     = (0, 0, 0)

# --- Grid layout (hexagram chain & goal) ---
CELL_W = 150       # horizontal step between hexagrams
CELL_H = 250       # vertical step between hexagrams
TOP_MARGIN = 90    # was 50; pushes grid down from the top

# --- Slots (visual placeholders) ---
SLOT_ROWS = 2      # two rows of slots

# Number of grid columns auto-fits window width
columns = WIDTH // CELL_W

# Left margin that centers the whole grid horizontally
SIDE_MARGIN = (WIDTH - (columns * CELL_W)) // 2

# Nudge the grid slightly to the right to counter the visual weight
HORIZONTAL_BIAS = 0  # tweak to taste (try 12–24)
grid_origin_x = SIDE_MARGIN + HORIZONTAL_BIAS
grid_origin_y = TOP_MARGIN

# --- Card styling ---
CARD_PAD = 8
CARD_RADIUS = 10
CARD_BORDER_W = 2
CHAIN_COLLECTED_BORDER_W = 4   # ⬅️ thicker yellow rim for collected cards in the chain

# After fonts are initialized
OPT_LABEL_GAP = max(1, CARD_BORDER_W + 0)

# Pending transform “card” state
pending_change = None  # dict or None
PENDING_DURATION_MS = 1000  # 2 seconds

# Colors
TEXT_COLOR = (0, 0, 0)
CARD_BG_DEFAULT = (255, 255, 255)           # white
CARD_BORDER_DEFAULT = (180, 180, 180)
CARD_BG_COLLECTED = (255, 236, 128)         # soft yellow
CARD_BORDER_COLLECTED = (200, 180, 80)
CARD_BG_FAILURE    = (235, 120, 120)   # soft red
CARD_BORDER_FAILURE= (200, 90, 90)

# Slightly-dim fill for past cards in the chain (lighter than inactive gray)
CHAIN_CARD_BG_DIM = (217, 217, 217)  # tweak 224–235 to taste

# "Goal → Deck" swoosh (runs after success popup appears)
ADD2DECK = None          # dict while animating; None otherwise
ADD2DECK_DONE = False    # prevents retrigger while the popup stays open
ADD2DECK_DURATION_MS = 600  # total time of the swoosh

# --- Goal → Start swoosh (triggered when COINS is pressed after a success)
GOAL2START = None                         # dict while animating; None otherwise
GOAL2START_DURATION_MS = 600              # tweak to taste

# --- Flip animation on card resolve ---
FLIP_MS = 220  # total duration of the flip (tweak 160–260ms to taste)
RESOLVE_FLIP = None   # {"started_at": int, "rect": pygame.Rect, "down_col": (r,g,b), "up_col": (r,g,b)}

# Live shortest distance from CURRENT card to the goal (recomputed each move)
LIVE_POSSIBLE_DIST = None

# --- Optimal streaks (hintless) ---
OPTIMAL_STREAK_CURR = 0  # consecutive hintless+optimal successes
OPTIMAL_STREAK_BEST = 0  # best streak this run

# Change button/card colors and shades
PURPLE = (128, 0, 128)      # whole
GREEN  = (50, 160, 90)      # lower
BLUE   = (70, 120, 220)     # upper

# --- Developer tools / cheats ---
DEV_TOOLS_ENABLED = False   # ← flip True only while developing

# --- Toolbar button colors (Deck / Hint / Help) ---
BTN_BG_DEFAULT       = (230, 230, 230)   # normal
BTN_BG_ACTIVE        = (210, 210, 210)   # toggled on (distinct from locked gray)
BTN_BG_LOCKED        = (80, 80, 80)      # disabled gray (used by Coins/Transforms)
BTN_BORDER           = (60, 60, 60)      # normal border
BTN_BORDER_ACTIVE    = (255, 255, 255)   # bright rim when active
BTN_TEXT             = (20, 20, 20)

BTN_RADIUS           = 0                 # <-- always square
BTN_BORDER_W         = 2
BTN_BORDER_W_ACTIVE  = 3
BTN_INNER_STROKE     = (245, 245, 245)   # subtle 1px inner stroke when active

# --- Win sequence (post-win “flip” placeholder) ---
WIN_SEQ_ACTIVE = False
WIN_SEQ_STARTED_AT = 0
WIN_SEQ_PER_CARD_MS = 100     # speed of the left→right hide
WIN_SEQ_LINGER_MS   = 100   # how long to linger on the last two
WIN_SEQ_START_DELAY_MS = 400   # ⬅️ new: pause before the gather starts (ms)
WIN_SEQ_MERGE_MS = 240  # how long the winning "sweep" lasts (ms)
SEQ_OUTCOME = None   # "success" or "failure"
WIN_CARD_INDEX= -1
SUCCESS_AWARD_MIN_IP = 1   # floor for any successful round (even with hints)

# Persistent flags
optimal_filled_wrong = False

AWARDS_GRANTED = False

POPUP_VISIBLE = False  # True only while the judgment popup is on-screen

# --- at module top ---
PENDING_ICON_SURF = None

# --- End-game test mode ---
ENDGAME_TEST_ARMED = False   # True => deck prefilled to 63; next success completes the set

def lighten(rgb, factor=0.7):
    # factor in [0..1] where 1 -> white
    r, g, b = rgb
    return (int(r + (255 - r) * factor),
            int(g + (255 - g) * factor),
            int(b + (255 - b) * factor))

def darken(rgb, amt=40):
    r, g, b = rgb
    return (max(0, r - amt), max(0, g - amt), max(0, b - amt))

# --- Dynamic buttons from TRANSFORMATIONS ---
BUTTON_W, BUTTON_H, BUTTON_PAD = 220, 56, 14
BUTTON_START_X, BUTTON_START_Y = 20, 16

# --- Coin flip logic ---
def generate_hexagram():
    """Generate a 6-bit hexagram using 50/50 yin-yang random lines."""
    return "".join(random.choice("01") for _ in range(6))

# --- Transformation Functions ---
def hu_gua(hexagram6):
    return hexagram6[1:4] + hexagram6[2:5]

def cuo_gua(hexagram6):
    return "".join("0" if c == "1" else "1" for c in hexagram6)

def cuo_ba_gua(hexagram6):
    # Invert only the lower trigram (first 3 bits)
    inverted_lower = "".join("0" if c == "1" else "1" for c in hexagram6[:3])
    return inverted_lower + hexagram6[3:]

def zong_gua(hexagram6):
    return hexagram6[::-1]

def yi_wei_gua(hexagram6):
    return hexagram6[-1] + hexagram6[:-1]

def jiao_gua(hexagram6):
    return hexagram6[3:] + hexagram6[:3]

def chong_ba_gua(hexagram6):
    # Duplicate the lower trigram into the upper trigram
    lower = hexagram6[:3]
    return lower + lower

def dui_chen_ba_gua(hexagram6):
    # Mirror lower trigram (bits 0–2) onto upper (bits 3–5)
    lower = hexagram6[:3]
    return lower + lower[::-1]

def zong_ba_gua(hexagram6):
    # Reverse only the lower trigram (first 3 bits)
    lower_reversed = hexagram6[:3][::-1]
    return lower_reversed + hexagram6[3:]

# Friendly names -> existing implementations
def shift_hexagram(h): return yi_wei_gua(h)        # 位卦
def flip_hexagram(h): return zong_gua(h)           # 综卦
def swap_hexagram(h): return jiao_gua(h)           # 交卦
def unhide_hexagram(h): return hu_gua(h)           # 核卦
def invert_hexagram(h): return cuo_gua(h)          # 错卦

def invert_lower_trigram(h): return cuo_ba_gua(h)  # 错八卦 (lower)
def flip_lower_trigram(h):   return zong_ba_gua(h) # 综八卦 (lower)
def mirror_onto_upper_trigram(h): return dui_chen_ba_gua(h)  # 对八卦 (lower → upper)
def copy_onto_upper_trigram(h):   return chong_ba_gua(h)     # 重八卦 (lower → upper)

# Ensure consistent ordering and labeling throughout
TRANSFORMATIONS = [
    # WHOLE (purple)
    {
        "short": "SHIFT",
        "card": "SHIFT (位卦 Yí Wèi Guà)",
        "desc": "Shift all lines up, top falls.",
        "scope": "whole",
        "char": "位卦",
        "pinyin": "Yí Wèi Guà",
        "color": PURPLE,
        "func": shift_hexagram,
    },
    {
        "short": "FLIP",
        "card": "FLIP (综卦 Zǒng Guà)",
        "desc": "Flip line order, all lines.",
        "scope": "whole",
        "char": "综卦",
        "pinyin": "Zǒng Guà",
        "color": PURPLE,
        "func": flip_hexagram,
    },
    {
        "short": "SWAP",
        "card": "SWAP (交卦 Jiāo Guà)",
        "desc": "Swap lower and upper trigrams.",
        "scope": "whole",
        "char": "交卦",
        "pinyin": "Jiāo Guà",
        "color": PURPLE,
        "func": swap_hexagram,
    },
    {
        "short": "UNHIDE",
        "card": "UNHIDE (核卦 Hu Guà)",
        "desc": "Unhide lines 2-4 ▼, lines 3-5 ▲.",
        "scope": "whole",
        "char": "核卦",
        "pinyin": "Hu Guà",
        "color": PURPLE,
        "func": unhide_hexagram,
    },
    {
        "short": "INVERT",
        "card": "INVERT (错卦 Cuò Guà)",
        "desc": "Invert yin ↔ yang, all lines.",
        "scope": "whole",
        "char": "错卦",
        "pinyin": "Cuò Guà",
        "color": PURPLE,
        "func": invert_hexagram,
    },

    # LOWER (green)
    {
        "short": "INVERT ▼",
        "card": "INVERT ▼ (错八卦 Cuò Bā Guà)",
        "desc": "Invert yin ↔ yang, lower trigram.",
        "scope": "lower",
        "char": "错八卦",
        "pinyin": "Cuò Bā Guà",
        "color": GREEN,
        "func": invert_lower_trigram,
    },
    {
        "short": "FLIP ▼",
        "card": "FLIP ▼ (综八卦 Zǒng Bā Guà)",
        "desc": "Flip line order, lower trigram.",
        "scope": "lower",
        "char": "综八卦",
        "pinyin": "Zǒng Bā Guà",
        "color": GREEN,
        "func": flip_lower_trigram,
    },

    # UPPER (blue)
    {
        "short": "MIRROR ▲",
        "card": "MIRROR ▲ (对八卦 Duìchèn Bā Guà)",
        "desc": "Mirror lower trigram onto upper.",
        "scope": "upper",
        "char": "对八卦",
        "pinyin": "Duìchèn Bā Guà",
        "color": BLUE,
        "func": mirror_onto_upper_trigram,
    },
    {
        "short": "COPY ▲",
        "card": "COPY ▲ (重八卦 Chóng Bā Guà)",
        "desc": "Copy lower trigram onto upper.",
        "scope": "upper",
        "char": "重八卦",
        "pinyin": "Chóng Bā Guà",
        "color": BLUE,
        "func": copy_onto_upper_trigram,
    },
]

# Initialize unlocked list based on TRANSFORMATIONS' "short" labels
TRANSFORM_UNLOCKED = [ (t["short"] in FREEBIE_SHORTS) for t in TRANSFORMATIONS ]

button_hitboxes = []  # [(rect, idx)]
by_scope = {"whole": [], "lower": [], "upper": []}
for idx, t in enumerate(TRANSFORMATIONS):
    by_scope[t["scope"]].append((idx, t))

def contrast_color(rgb):
    r, g, b = rgb
    # YIQ-ish luma
    return (0, 0, 0) if (r*299 + g*587 + b*114)/1000 > 150 else (255, 255, 255)

async def rebuild_buttons():
    global button_hitboxes
    button_hitboxes = []

    n = len(TRANSFORMATIONS)
    y = coins_button.bottom + 16  # row just below Coins

    MARGIN_X = 16
    max_row_width = WIDTH - 2 * MARGIN_X

    # we’ll try tighter gaps first to create width
    min_gap = 4
    max_gap = BUTTON_PAD
    gap = min_gap

    # start from generous width, then clamp
    max_btn_w = BUTTON_W
    min_btn_w = 96

    # find a gap / width pair that fits, preferring bigger buttons
    while True:
        btn_w = min(max_btn_w, max(min_btn_w, (max_row_width - (n - 1) * gap) // n))
        row_width = n * btn_w + (n - 1) * gap
        if row_width <= max_row_width or gap >= max_gap:
            break
        gap += 1  # very slightly loosen gap if we somehow still overflow
        await asyncio.sleep(0)  # <<< yield once per loop

    x = (WIDTH - row_width) // 2
    for idx, _t in enumerate(TRANSFORMATIONS):
        rect = pygame.Rect(x, y, btn_w, BUTTON_H)
        button_hitboxes.append((rect, idx))
        x += btn_w + gap

import pygame.freetype as ft

def _load_font_ft_or_classic(ttf_path, size, *, name_for_logs):
    """Try freetype Font first (web-friendly), then classic pygame.font.Font."""
    # Verify the file exists & is readable
    try:
        with open(ttf_path, "rb") as fp:
            _ = fp.read(8)
    except Exception as e:
        print(f"[font-missing] {name_for_logs} not readable at {ttf_path}: {e}")
        return None

    # Try freetype
    try:
        f = ft.Font(ttf_path, size)
        # sanity draw (2-arg API)
        _surf, _ = f.render("A", (0, 0, 0))
        return f
    except Exception as e:
        print(f"[font-freetype-failed] {name_for_logs}: {e}")

    # Fallback: classic pygame.font.Font
    try:
        f = pygame.font.Font(ttf_path, size)
        # sanity draw (3-arg API)
        _ = f.render("A", True, (0, 0, 0))
        return f
    except Exception as e:
        print(f"[font-classic-failed] {name_for_logs}: {e}")
        return None

def transforms_enabled():
# Usable only during an active round: after first toss, not locked,
# and no success/failure sequence or popup showing.
    return (
        game_started
        and not locked
        and not WIN_SEQ_ACTIVE
        and not POPUP_VISIBLE
        and GOAL2START is None   
    )

def draw_buttons(surface, font):
    enabled = transforms_enabled()

    # pulse used for hint ring
    pulse = 1.0
    if enabled and HINTS_ENABLED:
        t = pygame.time.get_ticks() / 250.0
        pulse = 1.0 + 0.6 * (0.5 + 0.5 * math.sin(t))

    # we’ll need a small font for the Buy labels
    small_font = TOOLTIP_FONT if 'TOOLTIP_FONT' in globals() else font

    for rect, idx in button_hitboxes:
        tdef = TRANSFORMATIONS[idx]

        style_enabled = enabled
        unlocked = TRANSFORM_UNLOCKED[idx]
        usable = style_enabled and unlocked

        # --- original visuals restored ---
        if usable:
            bg = lighten(tdef["color"], 0.75)
            border_col = darken(bg, 30)
            border_w = 1
        else:
            bg = BTN_BG_LOCKED
            border_col = BTN_BORDER
            border_w = 1

        # HINT ring only for usable buttons
        if usable and HINTS_ENABLED and (idx in optimal_next_buttons):
            border_w = max(2, int(3 * pulse))
            border_col = (255, 255, 140)

        pygame.draw.rect(surface, bg, rect, border_radius=10)
        pygame.draw.rect(surface, border_col, rect, border_w, border_radius=10)

        # label inside the button
        label = tdef["short"]
        surf = render_surf(font, label, (0, 0, 0))
        surface.blit(surf, surf.get_rect(center=rect.center))

        # --- Buy button under LOCKED transforms (Phase 1A) ---
        if style_enabled and (not unlocked) and SHOP_VISIBLE and (INSIGHT_BALANCE >= BUY_COST_CURRENT):
            buy_rect = get_buy_rect_for_transform(rect)
            affordable = (INSIGHT_BALANCE >= BUY_COST_CURRENT)

            # look: small rounded pill; light if affordable, dark if not
            if affordable:
                buy_bg = lighten(tdef["color"], 0.70)
                buy_border = darken(buy_bg, 35)
                buy_fg = (0, 0, 0)
            else:
                buy_bg = (90, 90, 90)
                buy_border = (70, 70, 70)
                buy_fg = (0, 0, 0)

            pygame.draw.rect(surface, buy_bg, buy_rect, border_radius=8)
            pygame.draw.rect(surface, buy_border, buy_rect, 1, border_radius=8)

            msg = f"Buy for {BUY_COST_CURRENT} IP"
            msg_surf = render_surf(small_font, msg, buy_fg)
            surface.blit(msg_surf, msg_surf.get_rect(center=buy_rect.center))

    # Informational message when Buy pills are not visible
    # Show if: round is underway AND (shop is closed OR not affordable yet)
    if game_started and (not SHOP_VISIBLE or INSIGHT_BALANCE < BUY_COST_CURRENT):
        small_font = globals().get("TOOLTIP_FONT", font)
        affordable = (INSIGHT_BALANCE >= BUY_COST_CURRENT)

        # Compute row geometry from the button rects
        row_left   = min(r.left   for (r, _) in button_hitboxes)
        row_right  = max(r.right  for (r, _) in button_hitboxes)
        row_bottom = max(r.bottom for (r, _) in button_hitboxes)
        center_x   = (row_left + row_right) // 2

        # Place a bit closer to the buttons than before
        y = row_bottom + 22

        if (not SHOP_VISIBLE) and affordable:
            # Wallet can afford, but shop is closed → show “beginning of the round”
            msg = "New change cards available for purchase at beginning of the next round."
            msg_surf = render_surf(small_font, msg, (230, 230, 230))
            surface.blit(msg_surf, msg_surf.get_rect(midtop=(center_x, y)))

        else:
            # Either shop is closed and not affordable yet, or shop is open but not affordable
            prefix   = "New change cards available for purchase at "
            cost_str = f"{BUY_COST_CURRENT} IP."

            prefix_surf = render_surf(small_font, prefix, (230, 230, 230))

            # Temporarily set bold for the cost part
            had_bold = getattr(small_font, "get_bold", lambda: False)()
            if hasattr(small_font, "set_bold"):
                small_font.set_bold(True)
            cost_surf = render_surf(small_font, cost_str, (230, 230, 230))
            if hasattr(small_font, "set_bold"):
                small_font.set_bold(had_bold)

            # Compose widths to center as a single unit
            total_w = prefix_surf.get_width() + cost_surf.get_width()
            start_x = center_x - total_w // 2

            surface.blit(prefix_surf, (start_x, y))
            surface.blit(cost_surf,   (start_x + prefix_surf.get_width(), y))



# Game state
hexagram_chain = []
goal_hexagram = None
transformation_limit = 10
locked = False
shortest_path_length = None
has_moved = False
hover_preview = None  # (button_rect, transformed_hexagram_dict, color)
game_started = False  # Track if coins button has been clicked
previous_goal_hexagram_binary = None
used_hexagrams = set()     # Track hexagrams used in this run
round_failed = False       # Tracks whether the player has failed
hexagrams_collected = 0
collected_hexagrams = set()
deck_popup_visible = False
deck_page = 0
coin_button_used = False
goal_revealed = False

# --- Run totals for the final-round message ---
RUN_TOTAL_MOVES = 0          # sum of moves across all completed rounds
RUN_TOTAL_OPTIMAL = 0        # sum of optimal moves (shortest_path_length) across completed rounds
RUN_TOTAL_INSIGHT = 0      # sum of per-round Insight Points (your formula)
RUN_TOTAL_SPENT = 0        # placeholder until spending mechanics exist

# --- Optimal guidance state (static vs live) ---
ROUND_START_BIN = None          # binary at round start
ROUND_OPTIMAL_DIST = None       # static 'optimal' distance used for label & popup

# Display-only counters / flags
DISPLAY_TOTAL_INSIGHT = 0      # what we show in the HUD; updates when the popup appears
POPUP_WAS_VISIBLE = False      # to detect the moment the popup turns on

# Hint usage tracking
HINTS_USED_THIS_ROUND = False  # becomes True if the Hint button is ever enabled in this round
RUN_HINTS_USED = False         # True if any round in the run used hints

# Spendable insight wallet (separate from total earned)
INSIGHT_BALANCE = 0

# Hints purchase/lock for the current round
HINTS_ENABLED = False                 # you likely already have this
HINTS_PURCHASED_THIS_ROUND = False

# Cost to enable Hints per round (Insight Points)
HINT_COST_IP = 1

# Round insight tracking
LAST_ROUND_INSIGHT = 0
LAST_ROUND_USED_HINTS = False

# Debug flag - set to True to enable console debugging
DEBUG_BUTTONS = False

# --- Hint system toggle ---
HINTS_ENABLED = False         # controlled by the toolbar Hint button
optimal_next_buttons = set()  # indices in TRANSFORMATIONS that are optimal right now

def debug_print(message):
    """Print debug messages only when DEBUG_BUTTONS is True"""
    if DEBUG_BUTTONS:
        print(message)

def has_glyph(f, ch):
    try:
        s = render_surf(f, ch, (0,0,0))
        return s.get_width() > 0
    except Exception:
        return False

LIGHTBULB = "💡" if has_glyph(symbol_font, "💡") else "★"  # or "✦", "☼", "ⓘ"

def _scale_to_height(surf, target_h):
    if not target_h: return surf
    h = surf.get_height()
    if h <= 0 or h == target_h: return surf
    new_w = max(1, int(surf.get_width() * (target_h / h)))
    return pygame.transform.smoothscale(surf, (new_w, target_h))

def render_surf(f, text, color, aa=True, size=None):
    # freetype path
    try:
        if size is not None:
            surf, _ = f.render(text, color, size=size)
        else:
            surf, _ = f.render(text, color)
        return surf
    except TypeError:
        # classic pygame.font.Font path
        surf = f.render(text, aa, color)
        if size is not None:
            surf = _scale_to_height(surf, size)
        return surf

def render_pair(f, text, color, aa=True, size=None):
    try:
        if size is not None:
            surf, rect = f.render(text, color, size=size)
        else:
            surf, rect = f.render(text, color)
        return surf, (rect or surf.get_rect())
    except TypeError:
        surf = f.render(text, aa, color)
        if size is not None:
            surf = _scale_to_height(surf, size)
        return surf, surf.get_rect()

# backward compat if you already used render_text earlier:
render_text = render_pair

def text_size(f, text, size=None):
    """(w,h) for both backends, without assuming .get_rect exists."""
    # freetype has get_rect; classic has size()
    try:
        import pygame.freetype as ft
        if isinstance(f, ft.Font):
            r = f.get_rect(text, size=size)
            return (r.width, r.height)
    except Exception:
        pass
    # classic or fallback
    try:
        return f.size(text)  # classic API
    except Exception:
        surf = render_surf(f, text, (0,0,0), size=size)
        return surf.get_width(), surf.get_height()

def draw_text_to(f, surface, pos, text, color, aa=True, size=None):
    """Draw text at pos for freetype or classic fonts; optional size target height."""
    # Try freetype's fast path
    try:
        if size is not None:
            f.render_to(surface, pos, text, color, size=size)
        else:
            f.render_to(surface, pos, text, color)
        return
    except Exception:
        # Fall back to render + blit
        surf = render_surf(f, text, color, aa=aa, size=size)
        surface.blit(surf, pos)

async def load_assets():
    global HEXAGRAM_DATA, ICON_SURF, font, TOOLTIP_FONT, chinese_font, symbol_font, hexagram_font

    if WEB:
        await asyncio.sleep(0)

    # JSON
    with open(resource_path("hexagrams.json"), "r", encoding="utf-8") as f:
        HEXAGRAM_DATA = json.load(f)

    # Icon (set later after set_mode)
    try:
        ICON_SURF = pygame.image.load(resource_path("iching.png")).convert_alpha()
    except Exception as e:
        print("Icon load failed:", e)

    # --- fonts you actually ship right now ---
    # main_ttf     = resource_path("fonts/Courier Regular.ttf")
    ui_ttf       = resource_path("fonts/dejavu-sans.ttf")   # you already ship this
    simsun_ttf   = resource_path("fonts/Simsun.ttf")
    seguisym_ttf = resource_path("fonts/seguisym.ttf")

    # UI fonts (classic is fine here)
    font = pygame.font.Font(ui_ttf, 12)
    TOOLTIP_FONT = pygame.font.Font(ui_ttf, max(10, int(font.get_height() * 0.85)))

    # Chinese font (prefer freetype; fallback to classic; finally to UI)
    chinese_font = _load_font_ft_or_classic(simsun_ttf, 28, name_for_logs="Simsun")
    if chinese_font is None:
        chinese_font = font

    # Symbol font (for the lightbulb; fallback to UI)
    symbol_font = _load_font_ft_or_classic(seguisym_ttf, 24, name_for_logs="seguisym")
    if symbol_font is None:
        symbol_font = font

    # Hexagram font
    hexagram_font = _load_font_ft_or_classic(ui_ttf, 24, name_for_logs="Hexagram (DejaVu)")
    if hexagram_font is None:
        hexagram_font = font

    print("assets loaded:", bool(HEXAGRAM_DATA))

def apply_transformation(transform_func, label, color=None, short=None):
    """Apply a transformation to the current hexagram"""
    global locked, has_moved, round_failed, goal_revealed, HINTS_ENABLED
    if hexagram_chain and not locked:
        prev = hexagram_chain[-1]
        new_binary = transform_func(prev["binary"])
        new_data = HEXAGRAM_DATA.get(new_binary)
        if new_data:
            has_moved = True
            hexagram_chain.append({
                "binary": new_binary,
                "number": new_data["number"],
                "unicode": new_data["unicode"],
                "name": new_data["name"],
                "transform_label": label,
                # NEW: edge metadata (arrow from prev → this)
                "edge_color": color,
                "edge_short": short,   # e.g., "INVERT ●" (optional to render)
            })
            # Use the passed-in color (from the transform button), lighten to match your button fill
            down_src = color if color is not None else (230, 230, 230)
            down_col = lighten(down_src, 0.75)
            start_resolve_flip_for(len(hexagram_chain) - 1, down_col)
            recompute_live_guidance()
            # one-move hint is consumed as soon as a move is made
            if HINTS_ENABLED:
                HINTS_ENABLED = False

            if not goal_revealed and new_binary == goal_hexagram["binary"]:
                goal_revealed = True
            # after you append the new card
            current_moves = len(hexagram_chain) - 1  # moves = chain length minus the starting card
            if (
                current_moves > transformation_limit
                and not (goal_hexagram and new_binary == goal_hexagram["binary"])
            ):
                locked = True
                round_failed = True
            debug_print(f"Applied transformation: {label} -> {new_binary}")
        else:
            debug_print(f"ERROR: No data found for hexagram {new_binary}")

async def reset_game(start_hexagram=None, full_reset=False):
    global buttons, button_definitions, hexagram_chain, goal_hexagram, hexagrams_collected, collected_hexagrams
    global locked, has_moved, shortest_path_length, help_popup_visible, goal_revealed, pending_change
    global game_started, previous_goal_hexagram_binary, used_hexagrams, round_failed
    global WIN_SEQ_ACTIVE, WIN_SEQ_STARTED_AT, POPUP_VISIBLE  
    global RUN_TOTAL_MOVES, RUN_TOTAL_OPTIMAL, RUN_TOTAL_INSIGHT, RUN_TOTAL_SPENT
    global SEQ_OUTCOME
    global HINTS_ENABLED, HINTS_USED_THIS_ROUND, RUN_HINTS_USED, HINTS_PURCHASED_THIS_ROUND, HINTS_COUNT_THIS_ROUND, RUN_HINTS_COUNT
    global DISPLAY_TOTAL_INSIGHT, POPUP_WAS_VISIBLE, INSIGHT_BALANCE
    global ADD2DECK, ADD2DECK_DONE
    global TRANSFORM_UNLOCKED, BUY_COST_CURRENT
    global AWARDS_GRANTED
    global SHOP_VISIBLE
    global OPTIMAL_STREAK_CURR, OPTIMAL_STREAK_BEST
    global ENDGAME_TEST_ARMED
    global optimal_filled_wrong

    debug_print("Resetting game...")
    game_started = True
    help_popup_visible = False
    has_moved = False
    goal_revealed = False
    pending_change = None
    round_failed = False  # reset failure flag by default
    POPUP_VISIBLE = False
    WIN_SEQ_ACTIVE = False
    WIN_SEQ_STARTED_AT = 0
    SEQ_OUTCOME = None
    HINTS_ENABLED = False
    HINTS_PURCHASED_THIS_ROUND = False
    HINTS_USED_THIS_ROUND = False
    POPUP_WAS_VISIBLE = False
    ADD2DECK = None
    AWARDS_GRANTED = False
    ADD2DECK_DONE = False
    SHOP_VISIBLE = True 
    HINTS_COUNT_THIS_ROUND = 0
    optimal_filled_wrong = False
    if full_reset:
        RUN_TOTAL_INSIGHT = 0
        RUN_TOTAL_SPENT   = 0
        RUN_TOTAL_MOVES   = 0
        RUN_TOTAL_OPTIMAL = 0
        RUN_HINTS_COUNT   = 0
        RUN_HINTS_USED    = False
        INSIGHT_BALANCE   = 0
        DISPLAY_TOTAL_INSIGHT = 0
        OPTIMAL_STREAK_CURR = 0
        OPTIMAL_STREAK_BEST = 0

        collected_hexagrams = set()
        hexagrams_collected = 0
        TRANSFORM_UNLOCKED = [ (t["short"] in FREEBIE_SHORTS) for t in TRANSFORMATIONS ]
        AWARDS_GRANTED = False
        RUN_HINTS_COUNT = 0
        BUY_COST_CURRENT = BUY_START_COST     # your starting cost knob
        SHOP_VISIBLE = False
        ENDGAME_TEST_ARMED = False

    # Reset used hexagrams if this is a fresh start
    if full_reset:
        used_hexagrams.clear()
    
    # Generate start hexagram
    if start_hexagram is None:
        # Choose new random start
        while True:
            collapsed = generate_hexagram()
            if collapsed in HEXAGRAM_DATA:
                break
            await asyncio.sleep(0)
    else:
        collapsed = start_hexagram

    hx_data = HEXAGRAM_DATA.get(collapsed)
    
    if hx_data:
        hexagram_chain = [{
            "binary": collapsed,
            "number": hx_data["number"],
            "unicode": hx_data["unicode"],
            "name": hx_data["name"],
            "transform_label": None
        }]
        locked = False
        debug_print(f"Start hexagram: {collapsed}")

    # Generate goal hexagram (must be unused and not same as start)
    possible_hexagrams = set(HEXAGRAM_DATA.keys()) - used_hexagrams - {collapsed}
    
    if not possible_hexagrams:
        print("All 64 hexagrams used! Game complete.")
        locked = True
        return

    collapsed_end = random.choice(list(possible_hexagrams))

    goal_data = HEXAGRAM_DATA.get(collapsed_end)
    if goal_data:
        goal_hexagram = {
            "binary": collapsed_end,
            "number": goal_data["number"],
            "unicode": goal_data["unicode"],
            "name": goal_data["name"]
        }
        debug_print(f"Goal hexagram: {collapsed_end}")

    recompute_optimal_guidance()

    # after you set the new start card and goal
    ROUND_START_BIN = collapsed  # <- set anchor for this round
    recompute_static_optimal(ROUND_START_BIN)  # static OPTIMAL distance
    recompute_live_guidance()                  # live hint rings

    # Reset help popup visibility
    help_popup_visible = False

    # 
    used_hexagrams.add(collapsed_end)
    previous_goal_hexagram_binary = collapsed_end

    # manage hexagram counter ONLY on full reset
    if full_reset:
        hexagrams_collected = 0  # initial toss resets the visible run counter

    # Reset win-sequence state
    WIN_SEQ_ACTIVE = False
    WIN_SEQ_STARTED_AT = 0
    POPUP_VISIBLE = False

    # Reset move counters
    if full_reset:
        used_hexagrams.clear()
        RUN_TOTAL_MOVES = 0          # <-- add
        RUN_TOTAL_OPTIMAL = 0        # <-- add
        RUN_TOTAL_INSIGHT = 0
        RUN_TOTAL_SPENT = 0

def handle_transformation_click(button_index):
    global pending_change
    if locked or pending_change is not None:
        return
    if 0 <= button_index < len(TRANSFORMATIONS):
        t = TRANSFORMATIONS[button_index]
        pending_change = {
            "started_at": pygame.time.get_ticks(),
            "name": t["short"],          # KEEP symbols like ●/▲/▼
            "label": t["card"],          # still kept, not used for headline now
            "desc": t["desc"],
            "color": t["color"],
            "transform_func": t["func"],
            "pinyin": t["pinyin"],       # <-- add
            "char": t["char"],           # <-- add
        }
        debug_print(f"Started pending change: {t['card']}")

async def handle_mouse_click(event_pos):
    """Centralized mouse click handling"""
    global help_popup_visible, hexagrams_collected, coin_button_used, HINTS_ENABLED, HINTS_USED_THIS_ROUND
    global HINTS_PURCHASED_THIS_ROUND, INSIGHT_BALANCE, RUN_TOTAL_SPENT, RUN_HINTS_USED, HINTS_COUNT_THIS_ROUND, RUN_HINTS_COUNT
    global BUY_COST_CURRENT, TRANSFORM_UNLOCKED
    global SHOP_VISIBLE
    global POPUP_VISIBLE, GOAL2START
    
    debug_print(f"Mouse click at: {event_pos}")
    
    # Coins button
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        mx, my = event.pos
        if coins_button.collidepoint(mx, my):
            # Only clickable before first toss, or from the judgment popup
            if (not game_started) or POPUP_VISIBLE:
                if not game_started or goal_hexagram is None:
                    # brand-new run
                    await reset_game(full_reset=True)
                else:
                    if SEQ_OUTCOME == "success":
                        deck_complete = (len(collected_hexagrams) >= 64)
                        if deck_complete:
                            # final success → start a fresh run
                            POPUP_VISIBLE = False
                            await reset_game(full_reset=True)
                        else:
                            # normal success → goal → start swoosh
                            POPUP_VISIBLE = False
                            GOAL2START = {
                                "started_at": pygame.time.get_ticks(),
                                # fill these next frame to avoid scope issues here:
                                "start_rect": None,
                                "end_rect":   None,
                                "start_bin":  goal_hexagram["binary"],
                            }
                    else:
                        # failure → fresh run (change to full_reset=False if you want to keep run state)
                        POPUP_VISIBLE = False
                        await reset_game(full_reset=True)
            return
    
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        if hint_icon_rect.collidepoint(event.pos):
            round_underway = game_started
            modal_open     = deck_popup_visible or help_popup_visible or POPUP_VISIBLE

            if round_underway and not modal_open:
                # We only purchase when it's currently OFF
                if not HINTS_ENABLED:
                    if INSIGHT_BALANCE >= HINT_COST_IP:
                        HINTS_ENABLED = True                  # turns on hint ring for the NEXT move only
                        INSIGHT_BALANCE -= HINT_COST_IP       # spend
                        RUN_TOTAL_SPENT += HINT_COST_IP
                        HINTS_COUNT_THIS_ROUND += 1           # count this hint
                        RUN_HINTS_COUNT        += 1
                        RUN_HINTS_USED          = True        # legacy flag for compatibility
                    else:
                        # insufficient IP → no-op (tooltip will show red)
                        pass
                else:
                    # already ON for the next move; cannot toggle off
                    pass
            return

    # only one popup at a time
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        mx, my = event.pos
        if help_button.collidepoint(mx, my):
            toggle_popup("help")
        elif deck_icon_rect.collidepoint(mx, my):
            toggle_popup("deck")

    # Buy buttons (unlock transforms persistently)
    if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
    and game_started and SHOP_VISIBLE and (INSIGHT_BALANCE >= BUY_COST_CURRENT)
    and not (deck_popup_visible or help_popup_visible or POPUP_VISIBLE)):
        mx, my = event.pos
        for rect, idx in button_hitboxes:
            if not TRANSFORM_UNLOCKED[idx]:
                buy_rect = get_buy_rect_for_transform(rect)
                if buy_rect.collidepoint((mx, my)):
                    # can we afford this purchase?
                    if INSIGHT_BALANCE >= BUY_COST_CURRENT:
                        cost = BUY_COST_CURRENT            # <-- capture current price
                        INSIGHT_BALANCE -= cost            # spend wallet
                        RUN_TOTAL_SPENT += cost            # <-- add to "spent" readout
                        TRANSFORM_UNLOCKED[idx] = True     # unlock permanently (this run)
                        BUY_COST_CURRENT += BUY_COST_STEP  # escalate for next purchase
                        recompute_live_guidance()
                        
                        # Reset static baseline BUT from the *current* card (not start) so it’s useful mid-round:
                        current_bin = hexagram_chain[-1]["binary"] if hexagram_chain else ROUND_START_BIN
                        recompute_static_optimal(anchor_bin=current_bin)
                        
                        # optional: feedback/sfx
                    return  # swallow the click either way

    # Transformation buttons (respect persistent unlock)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and hexagram_chain and not locked:
        mx, my = event.pos
        for rect, idx in button_hitboxes:
            if rect.collidepoint((mx, my)):
                if is_change_unlocked(idx):
                    # close the shop as soon as the first usable transform is pressed
                    SHOP_VISIBLE = False
                    handle_transformation_click(idx)
                # swallow the click either way once we hit a button area
                return
            
def get_hover_preview(mouse_pos):
    """Get hover preview information for transformation buttons, gated by IP and round state."""
    # Must be during a round and have a current hexagram
    if not game_started or locked or not hexagram_chain:
        return None

    current_binary = hexagram_chain[-1]["binary"]

    for rect, idx in button_hitboxes:
        if rect.collidepoint(mouse_pos):
            # Respect IP gate + modal state
            if not is_change_unlocked(idx):
                return None

            t = TRANSFORMATIONS[idx]
            try:
                preview_binary = t["func"](current_binary)
            except Exception:
                return None  # defensive: bad transform shouldn't crash hover

            hx_data = HEXAGRAM_DATA.get(preview_binary)
            if not hx_data:
                return None

            return (
                rect,
                {
                    "binary": preview_binary,
                    "number": hx_data["number"],
                    "name": hx_data["name"]["english"],
                },
                t["color"],
                idx,
            )
            # no need to keep looping once we found the hit
    return None

def wrap_two_lines(text, max_width, font):
    """Greedy 2-line wrap that preserves word order."""
    words = text.split()
    if not words:
        return "", None

    line1, line2 = "", ""
    in_second = False

    for w in words:
        if not in_second:
            test = (line1 + " " + w).strip()
            if font.size(test)[0] <= max_width:
                line1 = test
            else:
                # move this word to second line
                line2 = w
                in_second = True
        else:
            test2 = (line2 + " " + w).strip()
            if font.size(test2)[0] <= max_width:
                line2 = test2
            else:
                # truncate second line with ellipsis
                # trim until it fits with an ellipsis
                while font.size((line2 + "…").strip())[0] > max_width and " " in line2:
                    line2 = line2.rsplit(" ", 1)[0]
                if font.size((line2 + "…").strip())[0] > max_width:
                    # worst case: hard trim
                    while line2 and font.size((line2 + "…").strip())[0] > max_width:
                        line2 = line2[:-1]
                line2 = (line2 + "…").strip()
                break

    return line1, (line2 if line2 else None)

# multiline wrapper
def wrap_multiline(text, max_width, font):
    """Greedy wrap to as many lines as needed."""
    if not text:
        return []
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def wrap_three_lines(text, max_width, font):
    if not text:
        return "", "", ""
    # First get greedy lines
    lines = wrap_multiline(text, max_width, font)
    if len(lines) <= 3:
        # Always return exactly 3 slots (may be empty strings)
        return (lines + ["", "", ""])[:3]

    # Too many lines; fold the remainder into the 3rd, then fit with ellipsis
    first, second = lines[0], lines[1]
    third = " ".join(lines[2:])  # pack the rest into the 3rd
    ell = "…"

    # If even "…" doesn’t fit, hard-trim
    if font.size(ell)[0] > max_width:
        # fallback: show as much plain text as possible
        third = ""
        while third and font.size(third)[0] > max_width:
            third = third[:-1]
        return first, second, third

    # Trim until "third + ellipsis" fits
    while third and font.size((third + ell).strip())[0] > max_width:
        third = third[:-1]
    third = (third + ell).strip()
    return first, second, third

def toggle_popup(which):
    global help_popup_visible, deck_popup_visible
    if which == "help":
        new_state = not help_popup_visible
        help_popup_visible = new_state
        if new_state:
            deck_popup_visible = False
    elif which == "deck":
        new_state = not deck_popup_visible
        deck_popup_visible = new_state
        if new_state:
            help_popup_visible = False

def draw_modal_dim(screen, alpha=190):
    """Dim the entire screen (modal backdrop)."""
    w, h = screen.get_size()
    mask = pygame.Surface((w, h), flags=pygame.SRCALPHA)
    mask.fill((0, 0, 0, alpha))  # semi-transparent black
    screen.blit(mask, (0, 0))

def draw_toolbar_icons(screen):
    # states
    deck_active = deck_popup_visible
    help_active = help_popup_visible
    hint_active = HINTS_ENABLED

    # ---- Deck ----
    deck_bg = BTN_BG_ACTIVE if deck_active else BTN_BG_DEFAULT
    pygame.draw.rect(screen, deck_bg, deck_icon_rect, border_radius=BTN_RADIUS)
    pygame.draw.rect(
        screen,
        BTN_BORDER_ACTIVE if deck_active else BTN_BORDER,
        deck_icon_rect,
        BTN_BORDER_W_ACTIVE if deck_active else BTN_BORDER_W,
        border_radius=BTN_RADIUS
    )
    if deck_active:
        inner = deck_icon_rect.inflate(-4, -4)
        pygame.draw.rect(screen, BTN_INNER_STROKE, inner, 1, border_radius=BTN_RADIUS)
    deck_surf, _ = render_pair(hexagram_font, "䷀", BTN_TEXT)
    screen.blit(deck_surf, deck_surf.get_rect(center=deck_icon_rect.center))

    # ---- Hint (one-move purchase) ----
    round_underway = game_started
    modal_open     = deck_popup_visible or help_popup_visible or POPUP_VISIBLE

    style_enabled  = round_underway and not modal_open
    affordable     = (INSIGHT_BALANCE >= HINT_COST_IP)

    if not style_enabled:
        hint_bg, hint_border_col, hint_border_w, icon_color = BTN_BG_LOCKED, BTN_BORDER, BTN_BORDER_W, (20,20,20)
    elif HINTS_ENABLED:
        # Active (just purchased, for the next move)
        hint_bg, hint_border_col, hint_border_w, icon_color = BTN_BG_ACTIVE, BTN_BORDER_ACTIVE, BTN_BORDER_W_ACTIVE, (20,20,20)
    else:
        # OFF: enabled only if affordable; otherwise greyed out
        if affordable:
            hint_bg, hint_border_col, hint_border_w, icon_color = BTN_BG_DEFAULT, BTN_BORDER, BTN_BORDER_W, (20,20,20)
        else:
            hint_bg, hint_border_col, hint_border_w, icon_color = BTN_BG_LOCKED, BTN_BORDER, BTN_BORDER_W, (20,20,20)

    pygame.draw.rect(screen, hint_bg, hint_icon_rect, border_radius=BTN_RADIUS)
    pygame.draw.rect(screen, hint_border_col, hint_icon_rect, hint_border_w, border_radius=BTN_RADIUS)
    if style_enabled and HINTS_ENABLED:
        inner = hint_icon_rect.inflate(-4, -4)
        pygame.draw.rect(screen, BTN_INNER_STROKE, inner, 1, border_radius=BTN_RADIUS)

    # Icon
    hint_surf, _ = render_pair(symbol_font, LIGHTBULB, icon_color)
    screen.blit(hint_surf, hint_surf.get_rect(center=hint_icon_rect.center))

    # ---- Help ----
    help_bg = BTN_BG_ACTIVE if help_active else BTN_BG_DEFAULT
    pygame.draw.rect(screen, help_bg, help_button, border_radius=BTN_RADIUS)
    pygame.draw.rect(
        screen,
        BTN_BORDER_ACTIVE if help_active else BTN_BORDER,
        help_button,
        BTN_BORDER_W_ACTIVE if help_active else BTN_BORDER_W,
        border_radius=BTN_RADIUS
    )
    if help_active:
        inner = help_button.inflate(-4, -4)
        pygame.draw.rect(screen, BTN_INNER_STROKE, inner, 1, border_radius=BTN_RADIUS)
    help_surf, _ = render_pair(hexagram_font, "ℹ", BTN_TEXT)
    screen.blit(help_surf, help_surf.get_rect(center=help_button.center))

# --- Hover tooltip ---
TOOLTIP_PAD    = 6
TOOLTIP_RADIUS = 4
TOOLTIP_BORDER = (255, 255, 255)
TOOLTIP_TEXT   = (255, 255, 255)

def draw_tooltip(screen, text, anchor_rect, font, prefer_above=True, fg=None):
    if not text or not anchor_rect:
        return
    # Use override color if provided; otherwise fall back to your normal tooltip text color
    text_color = fg if fg is not None else TOOLTIP_TEXT

    # Render once with the chosen color
    text_surf = render_surf(font, text, text_color)

    # Size from the colored text surface
    box_w = text_surf.get_width()  + TOOLTIP_PAD * 2
    box_h = text_surf.get_height() + TOOLTIP_PAD * 2

    # Box surface with translucency
    box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    box.fill((0, 0, 0, 0))
    pygame.draw.rect(box, (0, 0, 0, 190), box.get_rect(), border_radius=TOOLTIP_RADIUS)
    pygame.draw.rect(box, TOOLTIP_BORDER, box.get_rect(), 1, border_radius=TOOLTIP_RADIUS)

    # Blit the colored text (this is the key change)
    box.blit(text_surf, (TOOLTIP_PAD, TOOLTIP_PAD))

    # Position
    WIDTH, HEIGHT = screen.get_size()
    x = anchor_rect.centerx - box_w // 2
    y = (anchor_rect.top - box_h - 6) if prefer_above else (anchor_rect.bottom + 6)

    if x < 4: x = 4
    if x + box_w > WIDTH - 4: x = WIDTH - 4 - box_w
    if prefer_above and y < 4:
        y = anchor_rect.bottom + 6

    screen.blit(box, (x, y))

def draw_add2deck_swoosh(screen, now):
    global ADD2DECK, ADD2DECK_DONE
    if ADD2DECK is None:
        return

    t = (now - ADD2DECK["started_at"]) / float(ADD2DECK_DURATION_MS)
    if t >= 1.0:
        ADD2DECK = None
        ADD2DECK_DONE = True
        return

    # ease-out for nicer motion
    u = 1.0 - (1.0 - t) * (1.0 - t)

    sr = ADD2DECK["start_rect"]
    er = ADD2DECK["end_rect"]

    cx = sr.centerx + u * (er.centerx - sr.centerx)
    cy = sr.centery + u * (er.centery - sr.centery)
    w  = int(sr.width  + u * (er.width  - sr.width))
    h  = int(sr.height + u * (er.height - sr.height))

    rect = pygame.Rect(0, 0, max(2, w), max(2, h))
    rect.center = (cx, cy)

    # bright yellow “card”
    pygame.draw.rect(screen, (255, 255, 140), rect, border_radius=CARD_RADIUS)
    pygame.draw.rect(screen, (255, 255, 140), rect, 3, border_radius=CARD_RADIUS)

def draw_hexagram_lines(
    screen, rect, bin_str,
    color=HEX_LINE_COLOR,
    line_thick=HEX_LINE_THICK,
    yin_gap_ratio=HEX_YIN_GAP_RATIO,
    corner=HEX_LINE_RADIUS,
    bottom_first=True,
    top_reserve_px=0,
    bottom_reserve_px=0,
    spacing_scale=1.0,
    valign=0.0,
    lead_gap_scale=1.0,
    y_offset_px=0,
    # NEW: fine control for tight previews
    inner_pad_x=None,         # override horizontal inner pad (px). None = use global HEX_INNER_PAD
    inner_pad_y=None,         # override vertical inner pad (px). None = use global HEX_INNER_PAD
    yin_gap_px=None,          # fixed center gap for yin lines (px). None = use yin_gap_ratio
    min_seg_w_px=8,           # minimum segment width for yin halves (px)
):
    """Draw 6 lines inside rect from bin_str (bottom_first encoding by default)."""
    # normalize order (your encoding is bottom-first)
    bits = bin_str[::-1] if bottom_first else bin_str
    bits = (bits + "000000")[:6]

    # inner box with optional per-axis padding
    pad_x = HEX_INNER_PAD if inner_pad_x is None else int(inner_pad_x)
    pad_y = HEX_INNER_PAD if inner_pad_y is None else int(inner_pad_y)
    inner = rect.inflate(-2 * pad_x, -2 * pad_y)

    # apply reserved space
    inner.y += int(top_reserve_px)
    inner.height = max(2, inner.height - int(top_reserve_px) - int(bottom_reserve_px))

    # vertical metrics
    line_h = max(2, int(line_thick))
    gap_y  = max(2, int(((inner.height - 6 * line_h) / 7) * spacing_scale))
    total_h = 6 * line_h + 7 * gap_y
    if total_h > inner.height:
        gap_y = max(2, (inner.height - 6 * line_h) // 7)
        total_h = 6 * line_h + 7 * gap_y

    slack = max(0, inner.height - total_h)
    y = inner.top + int(slack * max(0.0, min(1.0, valign)))
    y += int(gap_y * max(0.0, lead_gap_scale)) + int(y_offset_px)

    # horizontal metrics for yin gap / segments
    inner_w = max(2, inner.width)
    if yin_gap_px is None:
        center_gap = max(6, int(inner_w * max(0.0, min(0.9, yin_gap_ratio))))
    else:
        center_gap = max(2, int(yin_gap_px))

    # ensure segments have at least min_seg_w_px; shrink center gap if needed
    seg_w = (inner_w - center_gap) // 2
    if seg_w < min_seg_w_px:
        center_gap = max(2, inner_w - 2 * min_seg_w_px)
        seg_w = max(2, (inner_w - center_gap) // 2)

    # draw the six lines
    for ch in bits:
        if ch == "1":  # yang (solid)
            pygame.draw.rect(
                screen, color,
                pygame.Rect(inner.left, y, inner_w, line_h),
                border_radius=corner
            )
        else:          # yin (broken)
            left_rect  = pygame.Rect(inner.left,             y, seg_w, line_h)
            right_rect = pygame.Rect(inner.left + inner_w - seg_w, y, seg_w, line_h)
            pygame.draw.rect(screen, color, left_rect,  border_radius=corner)
            pygame.draw.rect(screen, color, right_rect, border_radius=corner)
        y += line_h + gap_y

# Vertical side label helper
def draw_side_label(screen, text, font, anchor_rect, side="left", pad=4, ccw=True, color=(230, 230, 230)):
    """
    Draw `text` rotated 90° next to `anchor_rect`.
    side: "left" or "right"
    ccw:  True = 90° counterclockwise, False = clockwise
    """
    label_surf = render_surf(font, text, color)
    rot = 90 if ccw else -90
    label_surf = pygame.transform.rotate(label_surf, rot)

    if side == "left":
        x = anchor_rect.left - pad - label_surf.get_width()
    else:
        x = anchor_rect.right + pad

    y = anchor_rect.centery - label_surf.get_height() // 2

    # Keep fully on-screen
    W, H = screen.get_size()
    if x < 2: x = 2
    if x + label_surf.get_width() > W - 2:
        x = W - 2 - label_surf.get_width()
    if y < 2: y = 2
    if y + label_surf.get_height() > H - 2:
        y = H - 2 - label_surf.get_height()

    screen.blit(label_surf, (x, y))

def is_change_unlocked(i):
    """A change button is usable iff the round is underway, no modal is open, and it's purchased/unlocked (or a freebie)."""
    round_underway = game_started
    modal_open = deck_popup_visible or help_popup_visible or POPUP_VISIBLE
    return round_underway and (not modal_open) and TRANSFORM_UNLOCKED[i]

def get_buy_rect_for_transform(button_rect):
    """Returns a small rect centered below a transform button."""
    w = button_rect.width
    x = button_rect.x
    y = button_rect.bottom + 6
    h = 24  # pill height
    return pygame.Rect(x, y, w, h)

def get_allowed_transform_indices():
    """Indices that are currently allowed by unlock state."""
    return [i for i, ok in enumerate(TRANSFORM_UNLOCKED) if ok]

def shortest_path_with_allowed(start_binary, goal_binary, allowed_indices):
    """
    BFS on 64 hexagrams using only transforms in allowed_indices.
    Returns (distance:int or None, first_moves:set[int]).
    If start==goal → (0, set()).
    """
    if start_binary == goal_binary:
        return 0, set()

    # Build quick access array of funcs in index order
    funcs = [TRANSFORMATIONS[i]["func"] for i in allowed_indices]

    # BFS state
    dist = {start_binary: 0}
    first_move = {start_binary: None}   # first transform index taken from the start to reach this node
    q = deque([start_binary])

    best_distance = None
    optimal_first_moves = set()

    while q:
        cur = q.popleft()
        d = dist[cur]

        # If we already found goal at distance best_distance, do not expand deeper layers
        if best_distance is not None and d >= best_distance:
            continue

        for k, idx in enumerate(allowed_indices):
            try:
                nxt = funcs[k](cur)
            except Exception:
                continue
            if not nxt:
                continue

            # Determine the first move to reach nxt
            fm = idx if cur == start_binary else first_move[cur]

            # First time we see nxt
            if nxt not in dist:
                dist[nxt] = d + 1
                first_move[nxt] = fm

                # If we reached the goal, record best distance and first move
                if nxt == goal_binary:
                    if best_distance is None:
                        best_distance = d + 1
                    if fm is not None:
                        optimal_first_moves.add(fm)

                # Only enqueue nodes up to best_distance
                if best_distance is None or (d + 1) <= best_distance:
                    q.append(nxt)

            # If we have seen nxt at the same depth (rare with pure BFS), still collect first moves
            elif nxt == goal_binary and dist[nxt] == d + 1 and fm is not None:
                optimal_first_moves.add(fm)

    return best_distance, optimal_first_moves

def recompute_optimal_guidance():
    """Updates shortest_path_length and optimal_next_buttons using only unlocked transforms."""
    global shortest_path_length, optimal_next_buttons

    if not goal_hexagram or not hexagram_chain:
        shortest_path_length = None
        optimal_next_buttons = set()
        return

    start_bin = hexagram_chain[-1]["binary"]
    goal_bin  = goal_hexagram["binary"]
    allowed   = get_allowed_transform_indices()

    dist, first_moves = shortest_path_with_allowed(start_bin, goal_bin, allowed)
    shortest_path_length = dist
    # belt-and-suspenders: filter by unlocks even though first_moves came from 'allowed'
    optimal_next_buttons = {i for i in (first_moves or set()) if i in allowed}

def recompute_static_optimal(anchor_bin=None):
    """
    Recompute the static 'optimal distance' used for the floating OPTIMAL tag
    and the round summary popup.

    anchor_bin:
      - None uses ROUND_START_BIN (or current card if empty)
      - Use current card when called immediately after a purchase mid-round
    """
    global ROUND_OPTIMAL_DIST
    if not goal_hexagram:
        ROUND_OPTIMAL_DIST = None
        return

    start_bin = (
        anchor_bin
        or ROUND_START_BIN
        or (hexagram_chain[-1]["binary"] if hexagram_chain else None)
    )
    if not start_bin:
        ROUND_OPTIMAL_DIST = None
        return

    allowed = get_allowed_transform_indices()
    dist, _ = shortest_path_with_allowed(start_bin, goal_hexagram["binary"], allowed)
    ROUND_OPTIMAL_DIST = dist

def recompute_live_guidance():
    """Update hint rings only (does NOT change the static OPTIMAL distance)."""
    global optimal_next_buttons, LIVE_POSSIBLE_DIST
    if not goal_hexagram or not hexagram_chain:
        optimal_next_buttons = set()
        LIVE_POSSIBLE_DIST = None
        return

    start_bin = hexagram_chain[-1]["binary"]
    goal_bin  = goal_hexagram["binary"]
    allowed   = get_allowed_transform_indices()

    dist, first_moves = shortest_path_with_allowed(start_bin, goal_bin, allowed)
    LIVE_POSSIBLE_DIST = dist                    # <-- add this
    optimal_next_buttons = set(first_moves or [])

def finalize_round_awards():
    """Award/record insight exactly once when the judgment popup opens."""
    global AWARDS_GRANTED, RUN_TOTAL_INSIGHT, INSIGHT_BALANCE, DISPLAY_TOTAL_INSIGHT
    global LAST_ROUND_INSIGHT, OPTIMAL_STREAK_CURR, OPTIMAL_STREAK_BEST

    # Guard: only do this once per round
    if AWARDS_GRANTED:
        return
    AWARDS_GRANTED = True

    # Compute round facts once
    current_moves = len(hexagram_chain) - 1
    optimal       = ROUND_OPTIMAL_DIST if ROUND_OPTIMAL_DIST is not None else current_moves
    was_optimal   = (ROUND_OPTIMAL_DIST is not None and current_moves == ROUND_OPTIMAL_DIST)
    was_hintless  = (HINTS_COUNT_THIS_ROUND == 0)

    # --- Update hintless optimal streak (once) ---
    if SEQ_OUTCOME == "success" and was_hintless and was_optimal:
        OPTIMAL_STREAK_CURR += 1
        if OPTIMAL_STREAK_CURR > OPTIMAL_STREAK_BEST:
            OPTIMAL_STREAK_BEST = OPTIMAL_STREAK_CURR
    else:
        OPTIMAL_STREAK_CURR = 0

    if SEQ_OUTCOME == "success":
        # Start from whatever base you computed earlier in the success path
        base = max(1, optimal * 2 - current_moves)

        bonus_optimal = OPTIMAL_BONUS_IP if was_optimal else 0
        bonus_streak  = OPTIMAL_STREAK_CURR
        penalty_hints = HINT_PENALTY_IP * HINTS_COUNT_THIS_ROUND

        gained_raw = base + bonus_optimal + bonus_streak - penalty_hints
        gained = max(SUCCESS_AWARD_MIN_IP, gained_raw)   # never below 1 on success
        LAST_ROUND_INSIGHT  = gained
        INSIGHT_BALANCE    += gained
        RUN_TOTAL_INSIGHT  += gained

    else:
        LAST_ROUND_INSIGHT = 0

    # Update the on-screen total display
    DISPLAY_TOTAL_INSIGHT = RUN_TOTAL_INSIGHT

def draw_hex_card_plain(surface, rect, hex_bin, alpha=255):
    """
    Draw a normal (non-yellow) card with hexagram lines into 'rect'.
    'alpha' applies to the whole card (0..255).
    """
    # Offscreen buffer so we can alpha the whole card cleanly
    buf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    # card body
    pygame.draw.rect(buf, (245, 245, 245), buf.get_rect(), border_radius=10)
    pygame.draw.rect(buf, (200, 200, 200), buf.get_rect(), 1, border_radius=10)
    # hexagram lines
    draw_hexagram_lines(
        buf, buf.get_rect(), hex_bin,
        line_thick=HEX_LINE_THICK,
        yin_gap_ratio=HEX_YIN_GAP_RATIO,
        corner=HEX_LINE_RADIUS,
    )
    if alpha < 255:
        buf.set_alpha(max(0, min(255, int(alpha))))
    surface.blit(buf, rect.topleft)

def render_full_card_surf(size, hx, *, bg, border, border_w, font):
    """Build a per-pixel-alpha surface that looks exactly like a normal card."""
    w, h = size
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    rect = pygame.Rect(0, 0, w, h)

    # Card shell
    pygame.draw.rect(surf, bg, rect, border_radius=CARD_RADIUS)
    pygame.draw.rect(surf, border, rect, border_w, border_radius=CARD_RADIUS)

    # Title (reserve exactly 3 rows like the chain/goal cards)
    name = hx["name"]["english"]
    number = hx["number"]
    full_title = f"{number}: {name}"

    max_width = rect.width - 16
    t1, t2, t3 = wrap_three_lines(full_title, max_width, font)

    title_y = 12
    line_h  = font.get_height()
    y = title_y
    for t in (t1, t2, t3):
        if t:
            ts = render_surf(font, t, TEXT_COLOR)
            tr = ts.get_rect(centerx=rect.centerx, y=y)
            surf.blit(ts, tr)
        y += line_h

    # Bars start on "row 4" – same as your normal cards
    top_reserve_px = 3 * line_h
    draw_hexagram_lines(
        surf, rect, hx["binary"],
        top_reserve_px=top_reserve_px,
        spacing_scale=1.10,          # keep in sync with your chain/goal usage
        valign=0.0
    )
    return surf

def draw_start_card_hold(screen, font):
    """Draw a full normal start card (white) in row 0, col 0, using the current goal hexagram data."""
    if not goal_hexagram:
        return
    start_col = 0
    start_row = 0
    sx = grid_origin_x + start_col * CELL_W
    sy = grid_origin_y + start_row * (CELL_H + GRID_ROW_GAP)
    start_card_rect = pygame.Rect(
        sx + CARD_PAD, sy + CARD_PAD,
        CELL_W - CARD_PAD * 2,
        CELL_H - CARD_PAD * 2
    )
    start_surf = render_full_card_surf(
        start_card_rect.size, goal_hexagram,
        bg=CARD_BG_DEFAULT,
        border=CARD_BORDER_DEFAULT,
        border_w=CARD_BORDER_W,
        font=font
    )
    screen.blit(start_surf, start_card_rect.topleft)

# --- Blinking "your move" arrow ---
PROMPT_ARROW_PERIOD_MS = 900   # blink period; tweak to taste
PROMPT_ARROW_CHAR = "→"        # swap for a triangle/emoji if you prefer

def get_chain_card_rect_at(index: int) -> pygame.Rect:
    """Inner card rect (with CARD_PAD) for chain slot 'index'."""
    col = index % columns
    row = index // columns
    x = grid_origin_x + col * CELL_W
    y = grid_origin_y + row * (CELL_H + GRID_ROW_GAP)
    return pygame.Rect(
        x + CARD_PAD, y + CARD_PAD,
        CELL_W - 2 * CARD_PAD, CELL_H - 2 * CARD_PAD
    )

def start_resolve_flip_for(index: int, down_color, up_color=None):
    """Begin a flip overlay centered on the given chain slot."""
    global RESOLVE_FLIP
    RESOLVE_FLIP = {
        "started_at": pygame.time.get_ticks(),
        "rect": get_chain_card_rect_at(index),
        "down_col": down_color,
        "up_col": (CARD_BG_DEFAULT if up_color is None else up_color),
        "index": index,  # ← add this
    }

def draw_resolve_flip(screen, now):
    """Overlay a quick horizontal 'card flip' (no face graphics)."""
    global RESOLVE_FLIP
    if not RESOLVE_FLIP:
        return

    t = (now - RESOLVE_FLIP["started_at"]) / float(FLIP_MS)
    if t >= 1.0:
        RESOLVE_FLIP = None
        return

    # Cosine width scale: 1 → 0 → 1 (classic flip profile)
    s = max(0.06, abs(math.cos(math.pi * t)))  # clamp so it never fully vanishes
    face_col = RESOLVE_FLIP["down_col"] if t < 0.5 else RESOLVE_FLIP["up_col"]

    dst = RESOLVE_FLIP["rect"]
    w = max(1, int(dst.width * s))
    h = dst.height

    # Draw a rounded slab centered on the card with a subtle border
    slab = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(slab, face_col, slab.get_rect(), border_radius=CARD_RADIUS)
    pygame.draw.rect(slab, (200, 200, 200), slab.get_rect(), 1, border_radius=CARD_RADIUS)
    screen.blit(slab, slab.get_rect(center=dst.center))

async def draw_goal2start_swoosh(screen, now):
    global GOAL2START
    if GOAL2START is None:
        return

    t = (now - GOAL2START["started_at"]) / float(GOAL2START_DURATION_MS)
    if t >= 1.0:
        start_bin = GOAL2START["start_bin"]
        GOAL2START = None
        # NEW: if completing the full set, start a fresh run
        if len(collected_hexagrams) >= 64:
            await reset_game(full_reset=True)
        else:
            await reset_game(start_hexagram=start_bin)
        return

    # ease-out
    u = 1.0 - (1.0 - t) * (1.0 - t)

    sr = GOAL2START["start_rect"]
    er = GOAL2START["end_rect"]

    cx = sr.centerx + u * (er.centerx - sr.centerx)
    cy = sr.centery + u * (er.centery - sr.centery)
    w  = int(sr.width  + u * (er.width  - sr.width))
    h  = int(sr.height + u * (er.height - sr.height))

    rect = pygame.Rect(0, 0, max(2, w), max(2, h))
    rect.center = (cx, cy)

    # match your “card” look (yellow body + rim)
    pygame.draw.rect(screen, (255, 255, 140), rect, border_radius=CARD_RADIUS)
    pygame.draw.rect(screen, (255, 255, 140), rect, 3, border_radius=CARD_RADIUS)

def arm_endgame_test(allow_goal_swap=True):
    """
    Prefill the Hexadeck to 63 unique hexagrams (missing exactly one).
    By default the missing one is the *current goal* so the next success will complete the deck.
    If the current goal is already collected, we optionally swap the goal to a missing one.
    """
    global ENDGAME_TEST_ARMED, collected_hexagrams, hexagrams_collected, goal_hexagram

    if not DEV_TOOLS_ENABLED:
        return

    if goal_hexagram is None:
        # Can't arm without a goal; silently ignore
        return

    # Build "all" set from your data
    all_bins = set(HEXAGRAM_DATA.keys())
    missing = goal_hexagram["binary"]

    # If goal already collected, pick any missing one and (optionally) switch the goal
    if missing in collected_hexagrams:
        alt = next((b for b in all_bins if b not in collected_hexagrams), None)
        if alt is None:
            # Already have all 64? Nothing to arm.
            return
        if allow_goal_swap:
            goal_hexagram = HEXAGRAM_DATA[alt]  # swap goal so next success will complete
            missing = alt
        else:
            # If you don't allow swapping, we can't guarantee the next success completes the set
            missing = alt

    # Prefill: everything except the "missing" one
    collected_hexagrams = (all_bins - {missing})
    # If you also track a numeric counter:
    if 'hexagrams_collected' in globals():
        hexagrams_collected = len(collected_hexagrams)

    ENDGAME_TEST_ARMED = True
    debug_print("[DEV] End-game test ARMED: deck set to 63; missing -> " + missing)

def recompute_layout_from_fonts():
    """Recalculate constants that depend on font metrics."""
    global GRID_ROW_GAP
    if font is None:
        return
    GRID_ROW_GAP = max(18, font.get_height())
    # If you have other metrics derived from fonts, recompute them here too.

def draw_centered_text(surface, text, font, y, width=WIDTH, color=(255, 255, 255)):
    text_surf, _ = render_pair(font, text, color)
    text_width = text_surf.get_width()
    x = (width - text_width) // 2  # Center the text horizontally
    surface.blit(text_surf, (x, y))

def draw_left_aligned_text(surface, text, font, y, margin=50, color=(255, 255, 255)):
    text_surf, _ = render_pair(font, text, color)
    surface.blit(text_surf, (margin, y))  # Left-aligned with a margin

# judgement popup helper
def draw_judgement_popup(
    screen, font, chinese_font, goal_hexagram, WIDTH, HEIGHT,
    grid_bounds, goal_rect, card_radius=12, content_rect=None,
    outcome="success"
):
    """
    Grid-shaped overlay with a rounded 'hole' over the goal hexagram.
    Shows SUCCESS (with judgment) or FAILURE (no judgment) content inside
    a centered narrow column (~2 cells wide).
    """
    if not grid_bounds or not goal_rect or not goal_hexagram:
        return

    # --- knobs ---
    OVERLAY_ALPHA = 255
    HOLE_PAD      = 8
    HOLE_BORDER_W = 3

    # 1) Build overlay over the grid area
    overlay = pygame.Surface((WIDTH, HEIGHT), flags=pygame.SRCALPHA)
    pygame.draw.rect(overlay, (40, 40, 40, OVERLAY_ALPHA), grid_bounds, border_radius=card_radius * 2)

    # 2) Punch transparent hole for the goal card
    hole_rect = goal_rect.inflate(HOLE_PAD, HOLE_PAD)
    pygame.draw.rect(overlay, (0, 0, 0, 0), hole_rect, border_radius=card_radius)

    # 3) Blit overlay
    screen.blit(overlay, (0, 0))

    # --- Corner caps: fill the rounded corners so the grid can't peek through ---
    corner_r = card_radius * 2  # must match the overlay's border_radius
    corner_caps = pygame.Surface((grid_bounds.width, grid_bounds.height), flags=pygame.SRCALPHA)

    # each cap = a solid square minus a transparent quarter-circle -> leaves a white "wedge"
    cap_color = (255, 255, 255, 255)

    def draw_corner_cap(surface, which):
        if which == "tl":
            square = pygame.Rect(0, 0, corner_r, corner_r)
            center = (corner_r, corner_r)
        elif which == "tr":
            square = pygame.Rect(surface.get_width() - corner_r, 0, corner_r, corner_r)
            center = (surface.get_width() - corner_r, corner_r)
        elif which == "bl":
            square = pygame.Rect(0, surface.get_height() - corner_r, corner_r, corner_r)
            center = (corner_r, surface.get_height() - corner_r)
        else:  # "br"
            square = pygame.Rect(surface.get_width() - corner_r, surface.get_height() - corner_r, corner_r, corner_r)
            center = (surface.get_width() - corner_r, surface.get_height() - corner_r)

        pygame.draw.rect(surface, cap_color, square)
        pygame.draw.circle(surface, (0, 0, 0, 0), center, corner_r)  # punch out the quarter-circle

    for pos in ("tl", "tr", "bl", "br"):
        draw_corner_cap(corner_caps, pos)

    # place the caps over the grid area
    screen.blit(corner_caps, (grid_bounds.left, grid_bounds.top))

    # 3.1) Outer white border around the popup (use same rounded shape as the mask)
    WHITE_BORDER_W = 3
    outer_rect = grid_bounds.inflate(-1, -1)  # tiny inset so edges look crisp
    pygame.draw.rect(
        screen, (255, 255, 255),
        outer_rect, WHITE_BORDER_W, border_radius=card_radius * 2
    )

    # 3.2) Border around the goal “hole” (yellow for success, red for failure)
    #hole_border_col = (255, 255, 0) if outcome == "success" else (235, 120, 120)
    #pygame.draw.rect(screen, hole_border_col, hole_rect, HOLE_BORDER_W, border_radius=card_radius)

    # --- data for this goal ---
    data = HEXAGRAM_DATA[goal_hexagram["binary"]]
    title = f'{data["number"]}: {data["name"]["english"]}'
    judgment = data["judgement"]
    chinese_char = data["name"]["chinese"]

    # --- narrow, centered column for the pre-message block ---
    if content_rect is None:
        w = int(grid_bounds.width * 0.4)  # ~40% width fallback
        content_rect = pygame.Rect(0, 0, w, grid_bounds.height - 16)
        content_rect.centerx = grid_bounds.centerx
        content_rect.top = grid_bounds.top + 8

    # colors
    YELLOW = (255, 255, 0)
    WHITE  = (240, 240, 240)
    DIM    = (200, 200, 200)
    RED    = (235, 120, 120)

    # helpers ------------------------------------------------------------
    def wrap_line(text, max_w):
        # Use existing wrap_multiline if available; otherwise a simple wrapper
        try:
            return wrap_multiline(text, max_w, font)
        except Exception:
            words, lines, cur = text.split(), [], ""
            for w in words:
                test = (cur + " " + w) if cur else w
                if font.size(test)[0] <= max_w:
                    cur = test
                else:
                    if cur: lines.append(cur)
                    cur = w
            if cur: lines.append(cur)
            return lines

    def blit_center_line(text, color, y):
        s = render_surf(font, text, color)
        r = s.get_rect(centerx=content_rect.centerx, y=y)
        screen.blit(s, r)
        return y + font.get_height()

    def blit_left_line(text, color, y, pad=0):
        x = content_rect.left + 10 + pad
        s = render_surf(font, text, color)
        screen.blit(s, (x, y))
        return y + font.get_height()

    def blit_kv(label, value_text, y):
        # label on left, value on right (aligned) inside the column
        x_left = content_rect.left + 10
        x_right = content_rect.right - 10
        sL = render_surf(font, label, WHITE);  screen.blit(sL, (x_left, y))
        sV = render_surf(font, value_text, WHITE)
        screen.blit(sV, (x_right - sV.get_width(), y))
        return y + font.get_height()
    
    # -------------------------------------------------------------------

    # pull game state safely
    chain = globals().get("hexagram_chain", [])
    current_moves = max(0, len(chain) - 1)
    optimal = globals().get("ROUND_OPTIMAL_DIST", None)
    if optimal is None:
        optimal = current_moves

    hexas_collected = globals().get("hexagrams_collected", 0)
    is_final = (hexas_collected >= 64)

    total_moves  = globals().get("RUN_TOTAL_MOVES", 0)
    total_opt    = globals().get("RUN_TOTAL_OPTIMAL", 0)
    total_gain   = globals().get("RUN_TOTAL_INSIGHT", 0)
    total_spent  = globals().get("RUN_TOTAL_SPENT", 0)

    # per-round insight (display only; accumulation happens elsewhere)
    insight_points = max(0, optimal * 2 - current_moves)  # original formula you asked for

    # === outcome branches ===
    cursor_y = content_rect.top
    wrap_w = content_rect.width - 20

    if outcome == "failure":
        # Header
        cursor_y = blit_center_line("", RED, cursor_y)
        cursor_y = blit_center_line("MISFORTUNE", RED, cursor_y)
        cursor_y += 6

        # Sentence
        msg = (
            f"You ran out of change slots. Your Hexadeck lies incomplete, "
            f"with {hexas_collected} of 64 hexagram{'s' if hexas_collected != 1 else ''} collected."
        )
        for line in wrap_line(msg, wrap_w):
            cursor_y = blit_left_line(line, WHITE, cursor_y)

        cursor_y += font.get_height() // 2

        # Run info box (cumulative)
        cursor_y = blit_center_line("=============RUN INFO==============", WHITE, cursor_y)
        cursor_y = blit_kv("You made:",              f"{RUN_TOTAL_MOVES} changes", cursor_y)
        cursor_y = blit_kv("Optimal was:",           f"{RUN_TOTAL_OPTIMAL} changes",   cursor_y)
        cursor_y = blit_kv("Hints used:", f"{globals().get('RUN_HINTS_COUNT', 0)} hint" + ("s" if globals().get('RUN_HINTS_COUNT', 0) != 1 else ""), cursor_y)
        cursor_y = blit_kv("Highest optimal streak (hintless):", f"{OPTIMAL_STREAK_BEST} rounds", cursor_y)
        cursor_y = blit_kv("Insight points gained:", f"+{RUN_TOTAL_INSIGHT}",        cursor_y)
        cursor_y = blit_kv("Insight points spent:",  f"+{RUN_TOTAL_SPENT}",        cursor_y)
        cursor_y = blit_center_line("=================================", DIM, cursor_y)
        cursor_y += font.get_height() // 3

        # Footer
        footer = "Care to try again? Use the Coins to start a new round."
        for line in wrap_line(footer, wrap_w):
            cursor_y = blit_left_line(line, WHITE, cursor_y)

        return  # IMPORTANT: no judgment text on failure

    # SUCCESS path (regular vs final round)
    if not is_final:
        # Header
        cursor_y = blit_center_line("", YELLOW, cursor_y)
        cursor_y = blit_center_line("SUCCESS!", YELLOW, cursor_y)
        cursor_y += 4

        # Sentence
        left_to_collect = max(0, 64 - hexas_collected)
        msg = (
            f"This hexagram has been added to your Hexadeck. You have "
            f"{left_to_collect} hexagram{'s' if left_to_collect != 1 else ''} left to collect."
        )
        for line in wrap_line(msg, wrap_w):
            cursor_y = blit_left_line(line, WHITE, cursor_y)
        cursor_y += font.get_height() // 2

        # Round info box
        cursor_y = blit_center_line("=============ROUND INFO=============", WHITE, cursor_y)
        cursor_y = blit_kv("You made:",               f"{current_moves} changes", cursor_y)
        cursor_y = blit_kv("Optimal was:",            f"{optimal} changes",       cursor_y)
        cursor_y = blit_kv("Hints used:", f"{globals().get('HINTS_COUNT_THIS_ROUND', 0)} hint" + ("s" if globals().get('HINTS_COUNT_THIS_ROUND', 0) != 1 else ""), cursor_y)
        cursor_y = blit_kv("Current optimal streak (hintless):", f"{OPTIMAL_STREAK_CURR} rounds", cursor_y)
        cursor_y = blit_kv("Insight points gained:",  f"+{LAST_ROUND_INSIGHT}",       cursor_y)
        cursor_y = blit_center_line("=================================", DIM, cursor_y)
        cursor_y += font.get_height() // 3

        # Post-note
        post = (
            "Spend your Insight Points to buy Hints, or save them to buy new Change Cards. "
            "When you're ready, use the Coins to cast the next Goal hexagram."
        )
        for line in wrap_line(post, wrap_w):
            cursor_y = blit_left_line(line, WHITE, cursor_y)

    else:
        # Final-round header
        cursor_y = blit_center_line("", YELLOW, cursor_y)
        cursor_y = blit_center_line("Success! You have completed your Hexadeck!", YELLOW, cursor_y)
        cursor_y += font.get_height() // 2

        # Run info box (cumulative)
        cursor_y = blit_center_line("=============RUN INFO=============", WHITE, cursor_y)
        cursor_y = blit_kv("You made:",              f"{RUN_TOTAL_MOVES} changes", cursor_y)
        cursor_y = blit_kv("Optimal was:",           f"{RUN_TOTAL_OPTIMAL} changes",   cursor_y)
        cursor_y = blit_kv("Hints used:", f"{globals().get('RUN_HINTS_COUNT', 0)} hint" + ("s" if globals().get('RUN_HINTS_COUNT', 0) != 1 else ""), cursor_y)
        cursor_y = blit_kv("Insight points gained:", f"+{RUN_TOTAL_INSIGHT}",        cursor_y)
        cursor_y = blit_kv("Insight points spent:",  f"+{RUN_TOTAL_SPENT}",        cursor_y)
        cursor_y = blit_center_line("=================================", DIM, cursor_y)
        cursor_y += font.get_height() // 3

        post = "Congratulations on completing the Hexadeck! Use the Coins to start a new round."
        for line in wrap_line(post, wrap_w):
            cursor_y = blit_left_line(line, WHITE, cursor_y)

    # small breathing room before title/judgment block
    cursor_y += 50

    # === Title, Judgment, Chinese (centered in the full grid area) ===
    title_surf = render_surf(font, title, YELLOW)
    title_rect = title_surf.get_rect(center=(grid_bounds.centerx, cursor_y))
    screen.blit(title_surf, title_rect)

    y = title_rect.bottom + 12
    for line in judgment.split("\n"):
        line_surf = render_surf(font, line, (255, 255, 255))
        line_rect = line_surf.get_rect(centerx=grid_bounds.centerx, y=y)
        screen.blit(line_surf, line_rect)
        y += 20

    chinese_surf, _ = render_pair(chinese_font, chinese_char, (255, 255, 255))
    chinese_rect = chinese_surf.get_rect(center=(grid_bounds.centerx, min(grid_bounds.bottom - 30, y + 28)))
    screen.blit(chinese_surf, chinese_rect)

# --- Main Loop ---
async def run_game():
    global ADD2DECK, ARROW_CHAR, ARROW_FONT, BLANK, DECK_POPUP_RECT, ENDGAME_TEST_ARMED, GRID_AREA_BOTTOM, GRID_AREA_TOP, HEADINGS, HEIGHT, HELP_POPUP_RECT, HINTS_ENABLED
    global LAST_ROUND_INSIGHT, LINE_STEP, MAX_LINES, MERGE_ACTIVE, OVERLAP, POPUP_VISIBLE, RUN_HINTS_USED, RUN_TOTAL_MOVES, RUN_TOTAL_OPTIMAL, SEQ_OUTCOME, START_CARD_RECT, WIDTH
    global WIN_CARD_INDEX, WIN_CARD_RECT, WIN_SEQ_ACTIVE, WIN_SEQ_STARTED_AT, _, active_color, allow, alpha, arrow_color, arrow_down_rect, arrow_h, arrow_rect
    global arrow_surf, arrow_up_rect, arrow_w, arrow_x, arrow_y, available_h, available_w, base, bg, border, border_w, box_bg
    global box_color, box_height, box_width, box_x, box_y, card_bg, card_border, card_rect, cell_info, center_x, center_y, ch_rect
    global ch_surf, chain_rows, char, coins_active, coins_color, coins_should_pulse, coins_text, col, col_gap, col_left, col_right, color
    global count_text, counter_text, cur, cur_y, current_hx, current_moves, cursor_y, cx, cy, deck_page, delay_elapsed, desc
    global dist, down_arrow, elapsed, ell, end_rect, eng, eng_rect, eng_surf, event, filled_and_wrong, full_title, gap_left
    global gap_right, gap_x, gap_y, gname, goal_card_bg, goal_card_border, goal_card_rect, goal_col, goal_is_collected, goal_is_yellow, goal_outer, goal_row_index
    global grid_bounds, grid_height, grid_origin_x, grid_origin_y, grid_rows, grid_width, gx, gy, help_text_lines, hexagrams_collected, hide_static_winner, hover_preview
    global hover_rect, hover_text, hover_text_color, hud_x, hud_y, hx, i, idx, impossible, info_surf, info_text, insight_text
    global insight_y, is_collected, is_current, is_failure_last, is_heading, is_last_card, is_winner, k, left, left_inner_right, left_rect, left_x
    global line, line1, line2, line_h, line_thick_preview, line_y, lines, lines_top, ln, ln_rect, ln_surf, locked
    global locked_color, made_optimal, margin_x, margin_y, max_row_index, max_text_w, max_w, max_width, merge_end_time, merge_start, merge_window, min_rows_for_slots
    global mouse_pos, moves_so_far, moving, msg, msg_color, mx, my, name, next_col, next_index, next_inner, next_outer
    global now, number, nxt, opt_color, opt_index, opt_x, opt_y, optimal, pad, pending_change, period, phase
    global pin_rect, pin_surf, pinyin, popup_height, popup_rect, popup_width, popup_x, popup_y, poss_color, poss_text, preview_h, preview_w
    global prompt, pulse, rect, rect1, rect2, remaining, right, right_rect, round_failed, row, running, s
    global seq_end_time, seq_start_time, slot_outer, slot_rect, sorted_hexes, sr, start_outer, start_rect, suppress_goal_draw, surf, surf1, surf2
    global sx, sy, symbol, symbol_rect, t, t1, t2, t3, t_eased, tag, tag_rect, tag_surf
    global target_index, tip_bg, tip_h, tip_pad_x, tip_pad_y, tip_rect, tip_w, tip_x, tip_y, title, title_row_h, title_rows
    global title_y, token, top_reserve_px, total_h, total_slots, total_to_hide, tr, ts, txt_color, ty, up_arrow, visible_hexes
    global white, win_hide_count, words, wrap_font, x, y
    global optimal_filled_wrong
    global screen
    global PENDING_ICON_SURF

    # ---- defer pygame import until runtime is ready ----
    global js
    try:
        import js as _real_js
        js = _real_js
    except Exception:
        class _NoopConsole:
            def log(self, *a, **k): pass
        class _NoJS:
            console = _NoopConsole()
            def __getattr__(self, name):
                def _noop(*a, **k): pass
                return _noop
        js = _NoJS()

    # ---- defer pygame import until the runtime is ready ----
    global pygame

    js.console.log("BOOT 0: run_game entered")

    # initialize pygame first; do NOT import submodules yet
    pygame.init()
    pygame.font.init()
    # if WEB: await asyncio.sleep(0)
    pygame.freetype.init()

    # tiny yield on web to let the FS & canvas settle
    import sys, asyncio as _asyncio
    try:
        if sys.platform == "emscripten" or getattr(sys, "_emscripten_info", None):
            await _asyncio.sleep(0)
    except Exception:
        pass

    js.console.log("BOOT 1: pygame inited & freetype ready")

    # now it's safe to create window, fonts, icons, etc.
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    if PENDING_ICON_SURF is not None:
        try:
            pygame.display.set_icon(PENDING_ICON_SURF)
        finally:
            PENDING_ICON_SURF = None
    pygame.display.set_caption("Hexadeck")
    js.console.log("BOOT 2: display set")

    # first paint
    screen.fill(BG_COLOR)
    pygame.display.flip()
    await _asyncio.sleep(0)
    js.console.log("BOOT 3: first paint ok")

    # then assets/fonts/buttons (your existing calls)
    await load_assets()
    js.console.log(f"BOOT 4: assets loaded? {bool(HEXAGRAM_DATA)}")

    recompute_layout_from_fonts()
    await rebuild_buttons()
    js.console.log("BOOT 5: buttons built")

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
    
            if event.type == pygame.KEYDOWN and DEV_TOOLS_ENABLED:
                if event.key == pygame.K_F12:  # pick any key you like
                    if not ENDGAME_TEST_ARMED:
                        arm_endgame_test(allow_goal_swap=True)
                    else:
                        # simple disarm; does not restore the exact prior deck (that’s fine for a dev tool)
                        ENDGAME_TEST_ARMED = False
                        debug_print("[DEV] End-game test DISARMED")
    
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
    
                if deck_popup_visible or help_popup_visible:
                    allow = False
    
                    # toolbar icons always allowed
                    if help_button.collidepoint(mx, my) or deck_icon_rect.collidepoint(mx, my) or hint_icon_rect.collidepoint(mx, my):
                        allow = True
    
                    # clicks inside the visible popup are allowed
                    if deck_popup_visible and DECK_POPUP_RECT and DECK_POPUP_RECT.collidepoint(mx, my):
                        allow = True
                    if help_popup_visible and HELP_POPUP_RECT and HELP_POPUP_RECT.collidepoint(mx, my):
                        allow = True
    
                    if not allow:
                        continue  # swallow click everywhere else while modal
    
            if event.type == pygame.MOUSEBUTTONDOWN:
                await handle_mouse_click(event.pos)
    
                if deck_popup_visible:
                    if arrow_up_rect.collidepoint(event.pos):
                        deck_page = 0
                    elif arrow_down_rect.collidepoint(event.pos):
                        deck_page = 1
    
        # Resolve pending change after duration
        now = pygame.time.get_ticks()
        if pending_change is not None:
            if now - pending_change["started_at"] >= PENDING_DURATION_MS:
                apply_transformation(
                    pending_change["transform_func"],
                    pending_change["label"],
                    color=pending_change.get("color"),
                    short=pending_change.get("name"),
                )
                pending_change = None
    
        # Get hover preview
        mouse_pos = pygame.mouse.get_pos()
        hover_preview = None if (deck_popup_visible or help_popup_visible) else get_hover_preview(mouse_pos)
        hover_text, hover_rect, hover_text_color = None, None, None
    
        # Tooltips only for the three toolbar icons
        if deck_icon_rect.collidepoint(mouse_pos):
            hover_text, hover_rect = "Hexadeck", deck_icon_rect
        elif hint_icon_rect.collidepoint(mouse_pos):
            hover_text = f"Hint (-{HINT_COST_IP} IP)"
            hover_rect = hint_icon_rect
            # Red when you can't afford and the hint isn't already active
            if game_started and not (deck_popup_visible or help_popup_visible or POPUP_VISIBLE):
                if (not HINTS_ENABLED) and (INSIGHT_BALANCE < HINT_COST_IP):
                    hover_text_color = (220, 60, 60)  # red
        elif help_button.collidepoint(mouse_pos):  # or help_button if that's your var
            hover_text, hover_rect = "Instructions", help_button
    
        # When drawing the tooltip, pass fg=hover_text_color
        if hover_text and hover_rect:
            draw_tooltip(screen, hover_text, hover_rect, font, prefer_above=True, fg=hover_text_color)
    
        # Begin drawing frame
        screen.fill(BG_COLOR)
    
        # --- Bottom-left counters (always visible) ---
        hud_x = 20
        hud_y = HEIGHT - 155
        white = (255, 255, 255)
    
        # Hexagrams collected (shows 0/64 before the first toss)
        counter_text = render_surf(font, f"Hexagrams Collected: {hexagrams_collected} of 64", white)
        screen.blit(counter_text, (hud_x, hud_y))
    
        # Insight Points (display total; updates when popup appears)
        insight_y = hud_y + font.get_height() + 4
        insight_text = render_surf(font, f"Insight Points (IP): {INSIGHT_BALANCE}", white)
        screen.blit(insight_text, (hud_x, insight_y))
    
        # Draw UI Buttons
        coins_text = render_surf(font, "Coins", (0, 0, 0))
        # Determine if Coins button should be active
        coins_active = (not game_started) or POPUP_VISIBLE
    
        # Pulse the Coins button on launch and after successful round popup
        coins_should_pulse = (not game_started) or POPUP_VISIBLE
        if coins_active and coins_should_pulse:
            t = pygame.time.get_ticks() / 250.0
            pulse = 1.0 + 0.6 * (0.5 + 0.5 * math.sin(t))
            pygame.draw.rect(screen, (255, 255, 140), coins_button, max(2, int(3 * pulse)))
    
        # Coins button colors
        active_color = (200, 200, 200)   # same as help/deck icons
        locked_color = (80, 80, 80)      # same as locked transformation buttons
    
        coins_color = active_color if coins_active else locked_color
        # Decide when to pulse the Coins outline
        coins_should_pulse = (not game_started) or POPUP_VISIBLE
    
        pygame.draw.rect(screen, coins_color, coins_button)  # fill first
    
        if (not game_started) or POPUP_VISIBLE:
            t = pygame.time.get_ticks() / 250.0
            pulse = 1.0 + 0.6 * (0.5 + 0.5 * math.sin(t))
            pygame.draw.rect(screen, (255, 255, 140), coins_button, max(2, int(3 * pulse)))
        else:
            pygame.draw.rect(screen, (60, 60, 60), coins_button, 2)
    
        coins_text = render_surf(font, "Coins", (0, 0, 0))
        screen.blit(coins_text, (coins_button.centerx - coins_text.get_width() // 2,
                                coins_button.centery - coins_text.get_height() // 2))
    
        draw_toolbar_icons(screen)
    
        # Draw transformation buttons
        draw_buttons(screen, font)
    
        # --- Dynamic grid origin per frame ---
        # columns already defined globally from CELL_W; keep that
        grid_width = columns * CELL_W
    
        # How many rows do we actually need?
        if hexagram_chain:
            chain_rows = ((len(hexagram_chain) - 1) // columns) + 1
        else:
            chain_rows = 1
    
        goal_row_index = 1  # you draw the goal on row 1
        min_rows_for_slots = SLOT_ROWS
        max_row_index = max(chain_rows - 1, goal_row_index, min_rows_for_slots - 1)
        grid_rows = max_row_index + 1
        grid_height = grid_rows * CELL_H + (grid_rows - 1) * GRID_ROW_GAP
    
        # Horizontal center in the window
        grid_origin_x = (WIDTH - grid_width) // 2
    
        # Vertical center between top of window and Coins button (with a small padding)
        GRID_AREA_TOP = 20
        GRID_AREA_BOTTOM = coins_button_y - 10
        available_h = max(0, GRID_AREA_BOTTOM - GRID_AREA_TOP)
        grid_origin_y = GRID_AREA_TOP + max(0, (available_h - grid_height) // 2)
        # Nudge the grid up a bit so the OPTIMAL label clears row 2
        grid_origin_y = max(GRID_AREA_TOP, grid_origin_y - GRID_ROW_GAP // 3)
    
        # Bounds of the full grid area (matching the two slot rows)
        grid_bounds = pygame.Rect(
            grid_origin_x + CARD_PAD,
            grid_origin_y + CARD_PAD,
            columns * CELL_W - 2 * CARD_PAD,
            SLOT_ROWS * CELL_H + (SLOT_ROWS - 1) * GRID_ROW_GAP - 2 * CARD_PAD
        )
    
        # --- Draw empty card slots (two rows * columns) ---
        for i in range(SLOT_ROWS * columns):
            col = i % columns
            row = i // columns
            x = grid_origin_x + col * CELL_W
            y = grid_origin_y + row * (CELL_H + GRID_ROW_GAP)
    
            slot_rect = pygame.Rect(
                x + CARD_PAD,
                y + CARD_PAD,
                CELL_W - CARD_PAD * 2,
                CELL_H - CARD_PAD * 2
            )
    
            # simple white rounded rect with a subtle border
            pygame.draw.rect(
                screen,
                CARD_BORDER_DEFAULT,
                slot_rect,
                CARD_BORDER_W,
                border_radius=CARD_RADIUS
            )
    
        # --- Draw the pending change card (occupies the next slot) ---
        if pending_change is not None:
            next_index = len(hexagram_chain)  # immediately to the right of current hexagram
            if next_index < SLOT_ROWS * columns:
                col = next_index % columns
                row = next_index // columns
                x = grid_origin_x + col * CELL_W
                y = grid_origin_y + row * (CELL_H + GRID_ROW_GAP)
    
                card_rect = pygame.Rect(
                    x + CARD_PAD,
                    y + CARD_PAD,
                    CELL_W - CARD_PAD * 2,
                    CELL_H - CARD_PAD * 2
                )
    
                # Card background = button color; border slightly darker
                bg = lighten(pending_change["color"], 0.75)
                border = darken(bg, 30)
    
                pygame.draw.rect(screen, bg, card_rect, border_radius=CARD_RADIUS)
                pygame.draw.rect(screen, border, card_rect, CARD_BORDER_W, border_radius=CARD_RADIUS)
    
                # --- 4-tier text layout ---
                txt_color = (0, 0, 0)
                line_h = font.get_height()
                BLANK  = line_h  # one extra blank line between elements
                cursor_y = card_rect.y + 10
                max_width = card_rect.width - 16
    
                # 1) English name WITH symbols, big and centered
                eng = pending_change.get("name", "")
                eng_surf = render_surf(font, eng, txt_color)
                eng_rect = eng_surf.get_rect(centerx=card_rect.centerx, y=cursor_y)
                screen.blit(eng_surf, eng_rect)
                cursor_y += eng_surf.get_height()
    
                # 2) Pinyin on its own line (centered)
                pinyin = pending_change.get("pinyin", "")
                if pinyin:
                    pin_surf = render_surf(font, pinyin, txt_color)
                    pin_rect = pin_surf.get_rect(centerx=card_rect.centerx, y=cursor_y)
                    screen.blit(pin_surf, pin_rect)
                    cursor_y += pin_surf.get_height() + BLANK + BLANK
    
                # 3) Chinese character on its own line (centered)
                char = pending_change.get("char", "")
                if char:
                    if chinese_font:
                        ch_surf, _ = render_pair(chinese_font, char, txt_color, size=line_h)  # same visual size as text
                    else:
                        ch_surf = render_surf(font, char, txt_color)
                    ch_rect = ch_surf.get_rect(centerx=card_rect.centerx, y=cursor_y)
                    screen.blit(ch_surf, ch_rect)
                    cursor_y += (ch_surf.get_height() if hasattr(ch_surf, "get_height") else line_h) + BLANK + BLANK
    
                # 4) Description (wrapped, centered)
                desc = pending_change.get("desc", "") or pending_change.get("description", "")
                if desc:
                    max_w = card_rect.width - 20  # you can tighten to -40 if edges feel tight
                    for line in wrap_multiline(desc, max_w, font):
                        ln_surf = render_surf(font, line, txt_color)
                        ln_rect = ln_surf.get_rect(centerx=card_rect.centerx, y=cursor_y)
                        screen.blit(ln_surf, ln_rect)             # <-- use the rect!
                        cursor_y = ln_rect.bottom                 # advance by actual rendered height
    
        # --- Slots-remaining message in the next empty slot ---
        if game_started and goal_hexagram and not locked:
            current_moves = (len(hexagram_chain) - 1) + (1 if pending_change is not None else 0)
            remaining = max(0, transformation_limit - current_moves)
    
            # Next slot index immediately after the current hexagram
            next_index = len(hexagram_chain) + (1 if pending_change is not None else 0)
    
            # Only draw if that slot exists in our 2-row (SLOT_ROWS) grid
            if next_index < SLOT_ROWS * columns:
                col = next_index % columns
                row = next_index // columns
                x = grid_origin_x + col * CELL_W
                y = grid_origin_y + row * (CELL_H + GRID_ROW_GAP)
    
                slot_rect = pygame.Rect(
                    x + CARD_PAD,
                    y + CARD_PAD,
                    CELL_W - CARD_PAD * 2,
                    CELL_H - CARD_PAD * 2
                )
    
                # Message text
                msg = f"You have {remaining} slot{'s' if remaining != 1 else ''} remaining."
                max_width = slot_rect.width - 16
    
                # Choose color: red if last 3 or fewer, else white
                if remaining <= 3:
                    msg_color = (240, 162, 164)  # bright red
                else:
                    msg_color = (255, 255, 255)  # white
    
                # Reuse your wrap helper
                line1, line2 = wrap_two_lines(msg, max_width, font)
    
                # Center the message inside the slot (no fill, just border)
                total_h = font.get_height() * (2 if line2 else 1)
                ty = slot_rect.y + (slot_rect.height - total_h) // 2
    
                surf1 = render_surf(font, line1, msg_color)
                rect1 = surf1.get_rect(centerx=slot_rect.centerx, y=ty)
                screen.blit(surf1, rect1)
    
                if line2:
                    surf2 = render_surf(font, line2, msg_color)
                    rect2 = surf2.get_rect(centerx=slot_rect.centerx, y=ty + font.get_height())
                    screen.blit(surf2, rect2)
    
        cell_info = []  # collect per-card layout info for arrow drawing
    
        # Display hexagram chain
        # How many chain cards (from the left) should be hidden this frame?
        win_hide_count = 0
        merge_start = 0
        merge_window = False
        if WIN_SEQ_ACTIVE:
            total_to_hide = max(0, len(hexagram_chain) - 1)  # hide everything except the last (the winner)
            elapsed = now - WIN_SEQ_STARTED_AT
    
            # pause before the gather starts
            delay_elapsed = max(0, elapsed - WIN_SEQ_START_DELAY_MS)
            win_hide_count = min(total_to_hide, delay_elapsed // WIN_SEQ_PER_CARD_MS)
    
            # success-only merge window (when the sweep should play)
            merge_start = WIN_SEQ_STARTED_AT + WIN_SEQ_START_DELAY_MS + total_to_hide * WIN_SEQ_PER_CARD_MS
            merge_window = (SEQ_OUTCOME == "success" and now >= merge_start and now < merge_start + WIN_SEQ_MERGE_MS)
        
        WIN_CARD_RECT = None
        WIN_CARD_INDEX = -1 
        
        START_CARD_RECT = None
    
        for i, hx in enumerate(hexagram_chain):
            # If the win sequence is playing, hide cards [0 .. win_hide_count-1].
            # The final card (i == len(chain)-1) is the yellow "winner" and should never be hidden.
            if WIN_SEQ_ACTIVE and i < win_hide_count:
                continue
            col = i % columns
            row = i // columns
            x = grid_origin_x + col * CELL_W
            y = grid_origin_y + row * (CELL_H + GRID_ROW_GAP)
    
            card_rect = pygame.Rect(
                x + CARD_PAD,
                y + CARD_PAD,
                CELL_W - CARD_PAD * 2,
                CELL_H - CARD_PAD * 2
            )
    
            # remember the first slot’s rect as the "start"
            if START_CARD_RECT is None and i == 0:
                START_CARD_RECT = card_rect.copy()
    
            # ... draw the card background, title, lines, etc ...
    
            if RESOLVE_FLIP and RESOLVE_FLIP.get("index") == i:
            # Do not draw this card yet; the flip overlay will cover this slot.
            # Also skip adding it to cell_info so the between-cards arrow doesn't appear yet.
                continue
    
            # Save for arrows
            cell_info.append({
                "rect": card_rect,
                "row": row,
                "col": col,
                "edge_color": hx.get("edge_color"),
                "edge_short": hx.get("edge_short"),
            })
    
            is_collected    = (hx["binary"] in collected_hexagrams)
            is_last_card    = (i == len(hexagram_chain) - 1)
            is_winner       = (goal_hexagram is not None and is_last_card and hx["binary"] == goal_hexagram["binary"])
            is_failure_last = (round_failed and locked and is_last_card)
    
            # Capture the winner’s rect and hide the static winner during the merge window
            if is_winner:
                WIN_CARD_RECT = card_rect.copy()
                WIN_CARD_INDEX = i
                # Hide the static winner from the end of the gather until the popup is visible
                hide_static_winner = (
                    WIN_SEQ_ACTIVE
                    and SEQ_OUTCOME == "success"
                    and is_winner and is_last_card
                    and (now >= merge_start)          # gather finished (covers merge AND linger)
                    and not POPUP_VISIBLE             # keep hidden until popup actually appears
                )
                if hide_static_winner:
                    continue
    
            # Background color
            is_current = is_last_card
    
            if is_failure_last:
                card_bg = CARD_BG_FAILURE
            elif is_winner:
                # current winning card gets the same yellow fill as the goal
                card_bg = CARD_BG_COLLECTED
            elif is_current and is_collected:
                # only the current card keeps yellow if it's a collected hexagram
                card_bg = CARD_BG_COLLECTED
            elif is_current:
                # current but not collected → normal white
                card_bg = CARD_BG_DEFAULT
            else:
                # any earlier card → lightly dimmed
                card_bg = CHAIN_CARD_BG_DIM
    
            # Border color + width
            if is_failure_last:
                card_border = CARD_BORDER_FAILURE
                border_w    = CARD_BORDER_W
            elif is_winner:
                card_border = CARD_BORDER_COLLECTED
                border_w    = CARD_BORDER_W            # normal width for the winner
            elif is_collected:
                card_border = CARD_BORDER_COLLECTED    # yellow border for previously collected
                border_w    = CARD_BORDER_W # thicker rim
            else:
                card_border = CARD_BORDER_DEFAULT
                border_w    = CARD_BORDER_W
    
            # Draw
            pygame.draw.rect(screen, card_bg, card_rect, border_radius=CARD_RADIUS)
            pygame.draw.rect(screen, card_border, card_rect, border_w, border_radius=CARD_RADIUS)
    
            # ---- CONTENT INSIDE THE CARD ----
            # Title: always reserve THREE lines; hexagram bars start on the 4th row
            name = hx["name"]["english"]
            number = hx["number"]
            full_title = f"{number}: {name}"
            max_width = card_rect.width - 16
            t1, t2, t3 = wrap_three_lines(full_title, max_width, font)
    
            title_y = card_rect.y + 12
            line_h  = font.get_height()
            cur_y   = title_y
    
            # render up to 3 lines; still advance cur_y even if the line is empty
            for t in (t1, t2, t3):
                if t:
                    ts = render_surf(font, t, TEXT_COLOR)
                    tr = ts.get_rect(centerx=card_rect.centerx, y=cur_y)
                    screen.blit(ts, tr)
                cur_y += line_h
    
            # Start the six “yao” bars on the 4th row (stable across cards)
            lines_top = title_y + line_h * 3 + 6  # +6 = small breathing room
    
            # Hexagram lines — centered within the card
            title_rows     = 3
            title_row_h    = font.get_height()
            top_reserve_px = title_rows * title_row_h
    
            draw_hexagram_lines(
                screen, card_rect, hx["binary"],
                top_reserve_px=top_reserve_px,
                spacing_scale=1.10,   # optional: open the vertical rhythm a touch
                valign=0.0,           # anchor toward top of usable box
                lead_gap_scale=0.6,   # smaller first gap pulls the stack upward
                y_offset_px=-2        # tiny nudge upward; tweak -1, -2, -3 to taste
            )
    
            draw_resolve_flip(screen, now)
    
            # --- Draw small right-facing arrows between adjacent cards on SAME ROW ---
            ARROW_CHAR = "►"   # or "➜" / "➤" / "►" if you prefer
            ARROW_FONT = font  # use your normal font; we can switch to a slightly smaller one if it feels big
    
            for k in range(1, len(cell_info)):
                left  = cell_info[k - 1]
                right = cell_info[k]
    
                # Only draw if same row (keeps visual clean; skip row wraps)
                if left["row"] != right["row"]:
                    # Special case: row 0 last col  →  row 1 first col
                    col_left  = left.get("col",  (left["rect"].left  - grid_origin_x) // CELL_W)
                    col_right = right.get("col", (right["rect"].left - grid_origin_x) // CELL_W)
                    if (left["row"] == 0 and right["row"] == 1
                        and col_left == (columns - 1) and col_right == 0):
    
                        arrow_color = right.get("edge_color") or (255, 255, 255)
    
                        left_inner_right = left["rect"].right
                        center_x = left_inner_right + CARD_PAD      # ← same spacing as between cards
                        center_y = left["rect"].centery
    
                        arrow_surf = render_surf(ARROW_FONT, ARROW_CHAR, arrow_color)
                        screen.blit(arrow_surf, arrow_surf.get_rect(center=(center_x, center_y)))
                    # Skip normal cross-row drawing
                    continue
    
                # Arrow uses the color that produced the RIGHT card
                arrow_color = right.get("edge_color") or (255, 255, 255)
                # arrow_color = (255, 255, 255)
    
                # Position: centered between the two cards, vertically centered on the cards
                gap_left  = left["rect"].right
                gap_right = right["rect"].left
                if gap_right <= gap_left:
                    continue  # no space (shouldn't happen with your layout)
    
                center_x = (gap_left + gap_right) // 2
                center_y = left["rect"].centery
    
                arrow_surf = render_surf(ARROW_FONT, ARROW_CHAR, arrow_color)
                arrow_rect = arrow_surf.get_rect(center=(center_x, center_y))
                screen.blit(arrow_surf, arrow_rect)
    
                # Optional: tiny label under the arrow (commented out to avoid clutter)
                # lbl = right.get("edge_short")
                # if lbl:
                #     lbl_surf = TOOLTIP_FONT.render(lbl, True, arrow_color)
                #     lbl_rect = lbl_surf.get_rect(center=(center_x, center_y + ARROW_FONT.get_height() // 2 + 2))
                #     screen.blit(lbl_surf, lbl_rect)
    
            # --- Blinking prompt arrow after the CURRENT card (same position as normal arrows) ---
            if (game_started
                and not POPUP_VISIBLE
                and not locked
                and not WIN_SEQ_ACTIVE
                and not (deck_popup_visible or help_popup_visible)
                and len(cell_info) >= 1):
    
                left = cell_info[-1]               # last placed card
                row  = left["row"]
                col  = left.get("col", None)
    
                # Derive next slot in SAME ROW (we never draw cross-row arrows)
                if col is None:
                    # if your cell_info doesn't store 'col', compute it from the rect:
                    col = (left["rect"].left - grid_origin_x) // CELL_W
    
                next_col = col + 1
                if next_col < columns and (len(hexagram_chain) <= transformation_limit):
                    # Build the next slot's inner rect (no card yet, but we know its geometry)
                    next_outer = pygame.Rect(
                        grid_origin_x + next_col * CELL_W,
                        grid_origin_y + row * (CELL_H + GRID_ROW_GAP),
                        CELL_W, CELL_H
                    )
                    next_inner = next_outer.inflate(-2 * CARD_PAD, -2 * CARD_PAD)
    
                    gap_left  = left["rect"].right
                    gap_right = next_inner.left
                    if gap_right > gap_left:
                        center_x = (gap_left + gap_right) // 2
                        center_y = left["rect"].centery
    
                        # Blink alpha (smooth sine)
                        period = PROMPT_ARROW_PERIOD_MS  # e.g., 900ms
                        phase  = (pygame.time.get_ticks() % period) / float(period)
                        alpha  = int(64 + 191 * (0.5 + 0.5 * math.sin(2 * math.pi * phase)))
    
                        # Use the SAME glyph/font as your normal arrows
                        ARROW_CHAR = "►"
                        ARROW_FONT = font
    
                        prompt = render_surf(ARROW_FONT, ARROW_CHAR, (255, 255, 255))
                        prompt.set_alpha(alpha)
                        screen.blit(prompt, prompt.get_rect(center=(center_x, center_y)))
    
                elif (next_col == columns and row == 0 and len(hexagram_chain) <= transformation_limit):
                    # Row wrap case: blink just one pad to the right of the last top-row card
                    left_inner_right = left["rect"].right
                    center_x = left_inner_right + CARD_PAD          # ← match spacing
                    center_y = left["rect"].centery
    
                    period = PROMPT_ARROW_PERIOD_MS
                    phase  = (pygame.time.get_ticks() % period) / float(period)
                    alpha  = int(64 + 191 * (0.5 + 0.5 * math.sin(2 * math.pi * phase)))
    
                    prompt = render_surf(ARROW_FONT, "►", (255, 255, 255))
                    prompt.set_alpha(alpha)
                    screen.blit(prompt, prompt.get_rect(center=(center_x, center_y)))
    
        # Display goal hexagram at far right
        if goal_hexagram:
            goal_col = columns - 1
            gx = grid_origin_x + goal_col * CELL_W
            gy = grid_origin_y + 1 * (CELL_H + GRID_ROW_GAP)
    
            # --- GOAL CARD COLORS (always set these before drawing the goal card) ---
            goal_is_collected = (SEQ_OUTCOME == "success" and POPUP_VISIBLE)  # ← add POPUP_VISIBLE
            goal_card_bg     = CARD_BG_COLLECTED  if goal_is_collected else CARD_BG_DEFAULT
            goal_card_border = CARD_BORDER_COLLECTED if goal_is_collected else CARD_BORDER_DEFAULT
    
            goal_card_rect = pygame.Rect(
                gx + CARD_PAD,
                gy + CARD_PAD,
                CELL_W - CARD_PAD * 2,
                CELL_H - CARD_PAD * 2
            )
    
            if GOAL2START:
                if GOAL2START.get("start_rect") is None:
                    GOAL2START["start_rect"] = goal_card_rect.copy()
                if GOAL2START.get("end_rect") is None:
                    GOAL2START["end_rect"] = get_chain_card_rect_at(0)
    
            goal_is_collected = goal_hexagram["binary"] in collected_hexagrams
            goal_is_yellow = (goal_revealed or goal_is_collected)
    
            if round_failed and locked:
                goal_card_bg = CARD_BG_FAILURE
                goal_card_border = CARD_BORDER_FAILURE
            else:
                goal_card_bg = CARD_BG_COLLECTED if goal_is_yellow else CARD_BG_DEFAULT
                goal_card_border = CARD_BORDER_COLLECTED if goal_is_yellow else CARD_BORDER_DEFAULT
    
            # DRAW THE GOAL CARD BACKGROUND + BORDER
            # DRAW THE GOAL CARD BACKGROUND + BORDER
            suppress_goal_draw = (GOAL2START is not None)   # ← ONLY hide during the coins swoosh
    
            if not suppress_goal_draw:
                pygame.draw.rect(screen, goal_card_bg, goal_card_rect, border_radius=CARD_RADIUS)
                pygame.draw.rect(screen, goal_card_border, goal_card_rect, CARD_BORDER_W, border_radius=CARD_RADIUS)
    
            # Title & lines INSIDE the goal card, centered
            gname = f"{goal_hexagram['number']}: {goal_hexagram['name']['english']}"
            max_width = goal_card_rect.width - 16
            t1, t2, t3 = wrap_three_lines(gname, max_width, font)
    
            title_y = goal_card_rect.y + 12
            line_h  = font.get_height()
            cur_y   = title_y
    
            for t in (t1, t2, t3):
                if t:
                    ts = render_surf(font, t, TEXT_COLOR)
                    tr = ts.get_rect(centerx=goal_card_rect.centerx, y=cur_y)
                    screen.blit(ts, tr)
                cur_y += line_h
    
            lines_top = title_y + line_h * 3 + 6  # start “yao” bars below the reserved title rows
    
            title_rows     = 3
            title_row_h    = font.get_height()
            top_reserve_px = title_rows * title_row_h
    
            draw_hexagram_lines(
                screen, goal_card_rect, goal_hexagram["binary"],
                top_reserve_px=top_reserve_px,
                spacing_scale=1.10,   # optional: open the vertical rhythm a touch
                valign=0.0,           # anchor toward top of usable box
                lead_gap_scale=0.6,   # smaller first gap pulls the stack upward
                y_offset_px=-2        # tiny nudge upward; tweak -1, -2, -3 to taste
            )
    
            # Check win condition and kick off win sequence once
            if goal_hexagram and hexagram_chain and hexagram_chain[-1]["binary"] == goal_hexagram["binary"]:
                # first time we notice the win this round
                if not WIN_SEQ_ACTIVE:
                    locked = True
                    WIN_SEQ_ACTIVE     = True
                    WIN_SEQ_STARTED_AT = now             # or pygame.time.get_ticks()
                    SEQ_OUTCOME        = "success"
    
                    # (optional) mark collected once
                    if goal_hexagram["binary"] not in collected_hexagrams:
                        collected_hexagrams.add(goal_hexagram["binary"])
                        hexagrams_collected += 1
                        if 'hexagrams_collected' in globals():
                            hexagrams_collected = len(collected_hexagrams)
    
                        if ENDGAME_TEST_ARMED and len(collected_hexagrams) >= 64:
                            ENDGAME_TEST_ARMED = False
                            debug_print("[DEV] End-game test completed -> DISARMED")
    
                    # --- accumulate totals ONCE ---
                    current_moves = len(hexagram_chain) - 1
                    optimal = shortest_path_length if shortest_path_length is not None else current_moves
    
                    base = max(1, optimal * 2 - current_moves)
                    LAST_ROUND_INSIGHT = base
    
                    RUN_TOTAL_MOVES   += current_moves
                    RUN_TOTAL_OPTIMAL += optimal
    
                    RUN_HINTS_USED |= LAST_ROUND_USED_HINTS
                    HINTS_ENABLED = False
                
                locked = True
    
        # --- Side labels: START (left of start slot), GOAL (right of goal slot) ---
    
        # Derive the START outer slot rect:
        if 'START_CARD_RECT' in globals() and START_CARD_RECT:
            # inflate inner card rect back to the slot box (outside the border)
            start_outer = START_CARD_RECT.inflate(2 * CARD_PAD, 2 * CARD_PAD)
        else:
            # Fallback: column 0, row 0 (the chain row)
            sx = grid_origin_x + 0 * CELL_W
            sy = grid_origin_y + 0 * (CELL_H + GRID_ROW_GAP)   # ⬅️ row 0
            start_outer = pygame.Rect(sx, sy, CELL_W, CELL_H)
    
        # Derive the GOAL outer slot rect (rightmost column, row 1 as you place goal)
        gx = grid_origin_x + (columns - 1) * CELL_W
        gy = grid_origin_y + 1 * (CELL_H + GRID_ROW_GAP)
        goal_outer = pygame.Rect(gx, gy, CELL_W, CELL_H)
    
        # Paint the labels just outside the slot borders
        draw_side_label(screen, "START", font, start_outer, side="left",  pad=8, ccw=True,  color=(230,230,230))
        draw_side_label(screen, "GOAL",  font, goal_outer,  side="right", pad=8, ccw=False, color=(230,230,230))
        
        # --- OPTIMAL marker ---
        optimal_broken = False

        if game_started and goal_hexagram and ROUND_OPTIMAL_DIST is not None and not POPUP_VISIBLE:

            moves_so_far = len(hexagram_chain) - 1

            optimal_still_possible = (
                LIVE_POSSIBLE_DIST is not None
                and moves_so_far + LIVE_POSSIBLE_DIST == ROUND_OPTIMAL_DIST
            )

            optimal_broken = not optimal_still_possible

            opt_index = ROUND_OPTIMAL_DIST
            total_slots = SLOT_ROWS * columns

            if 0 <= opt_index < total_slots:
                col = opt_index % columns
                row = opt_index // columns

                # Determine OPTIMAL color/state
                made_optimal = (
                    SEQ_OUTCOME == "success"
                    and moves_so_far == ROUND_OPTIMAL_DIST
                )

                if made_optimal:
                    opt_color = (255, 255, 0)          # yellow
                elif optimal_broken:
                    opt_color = (235, 120, 120)        # red
                else:
                    opt_color = (255, 255, 255)        # white

                # Slot rect
                opt_x = grid_origin_x + col * CELL_W
                opt_y = grid_origin_y + row * (CELL_H + GRID_ROW_GAP)
                slot_outer = pygame.Rect(opt_x, opt_y, CELL_W, CELL_H)

                # Render label
                tag = render_surf(font, "↓ OPTIMAL ↓", opt_color)
                tag_rect = tag.get_rect(
                    midbottom=(slot_outer.centerx, slot_outer.top - OPT_LABEL_GAP)
                )

                if tag_rect.top < 0:
                    tag_rect.top = 0

                screen.blit(tag, tag_rect)

                # Strikethrough immediately once optimal is broken
                if optimal_broken and not made_optimal:
                    y = tag_rect.centery
                    pad = 4
                    pygame.draw.line(
                        screen,
                        opt_color,
                        (tag_rect.left - pad, y),
                        (tag_rect.right + pad, y),
                        1
                    )


    
        # --- POSSIBLE / NOT POSSIBLE marker ---
        if game_started and goal_hexagram and not POPUP_VISIBLE and optimal_broken:

            moves_so_far = len(hexagram_chain) - 1
            remaining = max(0, transformation_limit - moves_so_far)
            dist = LIVE_POSSIBLE_DIST

            impossible = (dist is None) or (dist > remaining)

            if impossible:
                poss_text  = "↓ NOT POSSIBLE ↓"
                poss_color = (235, 120, 120)  # red
                target_index = transformation_limit
            else:
                poss_text  = "↓ POSSIBLE ↓"
                poss_color = (230, 230, 230)
                target_index = moves_so_far + dist

                # Achieved goal → yellow
                if SEQ_OUTCOME == "success" and dist == 0:
                    poss_color = (255, 255, 0)

            total_slots = SLOT_ROWS * columns
            if 0 <= target_index < total_slots:

                col = target_index % columns
                row = target_index // columns
                sx = grid_origin_x + col * CELL_W
                sy = grid_origin_y + row * (CELL_H + GRID_ROW_GAP)
                slot_outer = pygame.Rect(sx, sy, CELL_W, CELL_H)

                tag_surf = render_surf(font, poss_text, poss_color)
                tag_rect = tag_surf.get_rect(
                    midbottom=(slot_outer.centerx, slot_outer.top - OPT_LABEL_GAP)
                )

                # Clamp
                WIDTH, HEIGHT = screen.get_size()
                if tag_rect.top < 0: tag_rect.top = 0
                if tag_rect.right > WIDTH - 2: tag_rect.right = WIDTH - 2
                if tag_rect.left < 2: tag_rect.left = 2

                screen.blit(tag_surf, tag_rect)

    
        # Safety: if we filled the last slot and it's not the goal, mark failure
        if (
            not WIN_SEQ_ACTIVE
            and goal_hexagram
            and len(hexagram_chain) > 0
        ):
            current_moves = len(hexagram_chain) - 1
            if (
                current_moves >= transformation_limit
                and hexagram_chain[-1]["binary"] != goal_hexagram["binary"]
            ):
                locked = True
                round_failed = True
    
        # Failure sequence: include this round in cumulative totals (no awards yet)
        if round_failed and locked and not WIN_SEQ_ACTIVE:
            SEQ_OUTCOME = "failure"
            WIN_SEQ_ACTIVE = True
            WIN_SEQ_STARTED_AT = pygame.time.get_ticks()
    
            current_moves = len(hexagram_chain) - 1
            optimal = ROUND_OPTIMAL_DIST if ROUND_OPTIMAL_DIST is not None else current_moves
    
            base = max(1, optimal * 2 - current_moves)
            LAST_ROUND_INSIGHT = base
    
            RUN_TOTAL_MOVES   += current_moves
            RUN_TOTAL_OPTIMAL += optimal
            RUN_HINTS_USED    |= LAST_ROUND_USED_HINTS
            HINTS_ENABLED      = False
    
        # Draw hover preview box if applicable
        if hover_preview:
            rect, hx, box_color, idx = hover_preview
            box_width = rect.width
            box_height = 140
            box_x = rect.centerx - box_width // 2
            box_y = rect.top - box_height - 5  # 5px padding above button
            current_hx = hexagram_chain[-1]["binary"]
    
            # Rounded, lighter background; no border
            box_bg = lighten(box_color, 0.75)
            pygame.draw.rect(screen, box_bg, (box_x, box_y, box_width, box_height), border_radius=10)
    
            # --- Hexagram previews (bars) ---
            pad = 4
            col_gap = 6
    
            arrow_surf = render_surf(font, "→", (0, 0, 0))
            arrow_w = arrow_surf.get_width()
            arrow_h = arrow_surf.get_height()
    
            available_w = box_width - 2*pad - arrow_w - 2*col_gap
            preview_w   = max(42, available_w // 2)         # a touch wider than before
            preview_h   = box_height - 2*pad
    
            left_rect  = pygame.Rect(box_x + pad,                        box_y + pad, preview_w, preview_h)
            right_rect = pygame.Rect(box_x + box_width - pad - preview_w, box_y + pad, preview_w, preview_h)
    
            # arrow centered between previews
            arrow_x = (left_rect.right + right_rect.left - arrow_w) // 2
            arrow_y = box_y + (box_height - arrow_h) // 2 + 1
    
            # thinner bars for small previews
            line_thick_preview = max(0.5, int(preview_h / 40))  # ~3–4 px typically
    
            # Draw the two hexagrams with tighter horizontal padding and a small fixed yin gap
            draw_hexagram_lines(
                screen, left_rect, current_hx,
                line_thick=line_thick_preview,
                yin_gap_px=6,               # <- small fixed gap => longer segments
                inner_pad_x=4, inner_pad_y=6,
                spacing_scale=1.2,
                valign=0.0,
                lead_gap_scale=0.7
            )
    
            draw_hexagram_lines(
                screen, right_rect, hx["binary"],
                line_thick=line_thick_preview,
                yin_gap_px=6,
                inner_pad_x=4, inner_pad_y=6,
                spacing_scale=1.2,
                valign=0.0,
                lead_gap_scale=0.7
            )
    
            # Draw arrow last
            screen.blit(arrow_surf, (arrow_x, arrow_y))
    
            # --- description tooltip that visually extends the button (centered, smaller font) ---
            t = TRANSFORMATIONS[idx]
            tip_w = rect.width
            tip_pad_x = 8
            tip_pad_y = 6
            wrap_font = TOOLTIP_FONT  # use the smaller font for wrapping & rendering
    
            # Wrap description to button width minus padding
            desc = t["desc"]
            words = desc.split()
            lines = []
            cur = ""
            max_text_w = tip_w - tip_pad_x * 2
            while words:
                nxt = (cur + " " + words[0]).strip()
                if wrap_font.size(nxt)[0] <= max_text_w:
                    cur = nxt
                    words.pop(0)
                else:
                    if cur:
                        lines.append(cur)
                        cur = ""
                    else:
                        # emergency hard clip for one ultra-long token
                        token = words.pop(0)
                        while token and wrap_font.size(token)[0] > max_text_w:
                            token = token[:-1]
                        if token:
                            lines.append(token)
            if cur:
                lines.append(cur)
    
            # Optionally cap lines to avoid super tall tooltips (adds ellipsis)
            MAX_LINES = 3
            if len(lines) > MAX_LINES:
                lines = lines[:MAX_LINES]
                # add ellipsis to last line, clipping until it fits
                ell = "…"
                while wrap_font.size(lines[-1] + ell)[0] > max_text_w and len(lines[-1]) > 1:
                    lines[-1] = lines[-1][:-1]
                lines[-1] += ell
    
            tip_h = tip_pad_y * 2 + len(lines) * wrap_font.get_height()
    
            # Place tooltip so it overlaps the button — looks like a single block
            OVERLAP = 18
            tip_x = rect.x
            tip_y = rect.bottom - OVERLAP
    
            # Clamp bottom in case of very small windows
            if tip_y + tip_h > HEIGHT - 4:
                tip_y = max(4, HEIGHT - 4 - tip_h)
    
            tip_bg = lighten(t["color"], 0.75)
            tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
    
            pygame.draw.rect(screen, tip_bg, tip_rect, border_radius=10)
    
            # Center each line horizontally within the tooltip
            y = tip_rect.y + tip_pad_y
            for ln in lines:
                s = render_surf(wrap_font, ln, (0, 0, 0))
                sr = s.get_rect(centerx=tip_rect.centerx, y=y)
                screen.blit(s, sr)
                y += wrap_font.get_height()
    
        # --- SUCCESS FLOW (keep ONE copy of this; remove older variants) ---
        if WIN_SEQ_ACTIVE and goal_hexagram and hexagram_chain:
            total_to_hide   = max(0, len(hexagram_chain) - 1)  # hide all but the last card (the winner)
            seq_start_time  = WIN_SEQ_STARTED_AT + WIN_SEQ_START_DELAY_MS
            seq_end_time    = seq_start_time + total_to_hide * WIN_SEQ_PER_CARD_MS
            merge_end_time  = seq_end_time + WIN_SEQ_MERGE_MS
    
            now = pygame.time.get_ticks()
    
            if SEQ_OUTCOME == "success" and WIN_CARD_RECT:
                if seq_end_time <= now < merge_end_time:
                    # MERGE SWEEP (draw moving highlight; do NOT draw popup yet)
                    MERGE_ACTIVE = True
                    t = (now - seq_end_time) / float(WIN_SEQ_MERGE_MS)  # 0→1
                    t_eased = 1.0 - (1.0 - t) * (1.0 - t)               # easeOutQuad
    
                    moving = WIN_CARD_RECT.copy()
                    cx = WIN_CARD_RECT.centerx + t_eased * (goal_card_rect.centerx - WIN_CARD_RECT.centerx)
                    cy = WIN_CARD_RECT.centery + t_eased * (goal_card_rect.centery - WIN_CARD_RECT.centery)
                    moving.center = (cx, cy)
    
                    pygame.draw.rect(screen, (255, 255, 140), moving, 5, border_radius=CARD_RADIUS)
                    pygame.draw.rect(screen, (255, 255, 140), moving.inflate(10, 10), 2, border_radius=CARD_RADIUS)
                else:
                    MERGE_ACTIVE = False
                    # after merge + linger, show the popup
                    if now >= merge_end_time + WIN_SEQ_LINGER_MS and not POPUP_VISIBLE:
                        finalize_round_awards()          # ← add this line
                        POPUP_VISIBLE = True
    
                        # Kick off "goal → deck" swoosh once, right as the popup appears
                        if SEQ_OUTCOME == "success" and ADD2DECK is None:
                            start_rect = goal_card_rect.copy()
    
                            # end at a small rectangle inside the deck icon
                            end_rect = deck_icon_rect.inflate(-deck_icon_rect.width // 2,
                                                            -deck_icon_rect.height // 2)
                            if end_rect.width < 10 or end_rect.height < 10:
                                end_rect = deck_icon_rect.inflate(-deck_icon_rect.width // 3,
                                                                -deck_icon_rect.height // 3)
                            end_rect.center = deck_icon_rect.center
    
                            ADD2DECK = {
                                "started_at": now,
                                "start_rect": start_rect,
                                "end_rect":   end_rect,
                            }
                            # optional: if you’re using it
                            # ADD2DECK_DONE = False
                        
            else:
                # failure path (or no WIN_CARD_RECT): show popup after gather + linger (no merge)
                if now >= seq_end_time + WIN_SEQ_LINGER_MS and not POPUP_VISIBLE and SEQ_OUTCOME == "failure":
                    POPUP_VISIBLE = True
                    finalize_round_awards()   # <- award once here
    
        # --- POPUPS / DIMMER / MODALS (single consolidated block) ---
    
        # (Tip) compute once per frame so all animations use the same timestamp
        now = pygame.time.get_ticks()
    
        if deck_popup_visible or help_popup_visible:
            # 0) If the judgment popup is up, draw it FIRST so it sits UNDER the dimmer
            if POPUP_VISIBLE and goal_hexagram:
                draw_judgement_popup(
                    screen, font, chinese_font,
                    goal_hexagram, WIDTH, HEIGHT,
                    grid_bounds, goal_card_rect,
                    CARD_RADIUS,
                    outcome=SEQ_OUTCOME
                )
    
            # 2) Draw the goal→deck swoosh UNDER the dimmer as well (so it gets darkened)
            draw_add2deck_swoosh(screen, now)
    
            # 6) Full-screen dim (darkens board + popup + swoosh)
            draw_modal_dim(screen, alpha=190)  # tweak 170–200 to taste
    
            # 7) Top-most UI for the Deck/Help modal
            draw_toolbar_icons(screen)
            if hover_text and hover_rect:
                draw_tooltip(screen, hover_text, hover_rect, font, prefer_above=True)
    
            # 8) (Wherever you currently draw the Deck/Help popup contents) — keep those here, ABOVE the dimmer
            # draw_deck_popup(...) / draw_help_popup(...)
    
        else:
            # No other modal → draw the judgment popup normally on top of the board
            if POPUP_VISIBLE and goal_hexagram:
                draw_judgement_popup(
                    screen, font, chinese_font,
                    goal_hexagram, WIDTH, HEIGHT,
                    grid_bounds, goal_card_rect,
                    CARD_RADIUS,
                    outcome=SEQ_OUTCOME
                )
            # Then draw the swoosh on top of the popup
            draw_add2deck_swoosh(screen, now)
            await draw_goal2start_swoosh(screen, now)
    
    
        # --- Deck popup state ---
        # Arrow button rectangles (top-right corner inside popup)
        popup_width = 580
        popup_height = 510
        popup_x = (WIDTH - popup_width) // 2
        popup_y = 38
        arrow_up_rect = pygame.Rect(popup_x + popup_width - 30, popup_y + 10, 20, 20)
        arrow_down_rect = pygame.Rect(popup_x + popup_width - 30, popup_y + 35, 20, 20)
    
        # --- Deck popup rendering ---
        if deck_popup_visible:
            popup_rect = pygame.Rect(popup_x, popup_y, popup_width, popup_height)
            DECK_POPUP_RECT = popup_rect  # <-- set global hit area
    
            pygame.draw.rect(screen, (40, 40, 40), DECK_POPUP_RECT)
            pygame.draw.rect(screen, (255, 255, 255), DECK_POPUP_RECT, 2)
    
            # Title and count
            title = render_surf(font, "HEXADECK", (255, 255, 255))
            screen.blit(title, (popup_x + popup_width // 2 - title.get_width() // 2, popup_y + 10))
    
            count_text = render_surf(font, f"{hexagrams_collected} of 64 collected", (255, 255, 255))
            screen.blit(count_text, (popup_x + popup_width // 2 - count_text.get_width() // 2, popup_y + 30))
    
            # Arrow buttons
            pygame.draw.rect(screen, (200, 200, 200), arrow_up_rect)
            pygame.draw.rect(screen, (200, 200, 200), arrow_down_rect)
            up_arrow = render_surf(font, "▲", (0, 0, 0))
            down_arrow = render_surf(font, "▼", (0, 0, 0))
            screen.blit(up_arrow, (arrow_up_rect.centerx - up_arrow.get_width() // 2, arrow_up_rect.centery - up_arrow.get_height() // 2))
            screen.blit(down_arrow, (arrow_down_rect.centerx - down_arrow.get_width() // 2, arrow_down_rect.centery - down_arrow.get_height() // 2))
    
            # Deck grid
            margin_x = 20
            margin_y = 60
            gap_x = 135
            gap_y = 45
    
            sorted_hexes = sorted(HEXAGRAM_DATA.items(), key=lambda x: x[1]["number"])
            if deck_page == 0:
                visible_hexes = sorted_hexes[:40]
            else:
                visible_hexes = sorted_hexes[40:]
    
            for i, (binary, data) in enumerate(visible_hexes):
                row = i // 4
                col = i % 4
                x = popup_x + margin_x + col * gap_x
                y = popup_y + margin_y + row * gap_y
    
                color = (255, 255, 0) if binary in collected_hexagrams else (255, 255, 255)
    
                symbol = data["unicode"]

                # width/height without assuming freetype:
                w, h = text_size(hexagram_font, symbol)          # or text_size(hexagram_font, symbol, size=line_h)
                symbol_rect = pygame.Rect(x, y, w, h)

                # render at the same topleft:
                draw_text_to(hexagram_font, screen, symbol_rect.topleft, symbol, color)  # add size=... if you used one
    
                number = str(data["number"])
                name = data["name"]["english"]
                info_text = f"{number} {name}"
                max_width = 100
                while font.size(info_text)[0] > max_width and len(name) > 1:
                    name = name[:-1]
                    info_text = f"{number} {name}"
                info_surf = render_surf(font, info_text, color)
    
                screen.blit(info_surf, (x + symbol_rect.width + 5, y))
    
        else:
            DECK_POPUP_RECT = None  # <-- clear when not visible    
    
        # Draw help popup if visible
        if help_popup_visible:
            popup_width = 580
            popup_height = 510  # Increased height to accommodate all lines
            popup_x = (WIDTH - popup_width) // 2
            popup_y = 38  # Top-aligned to avoid covering Coins + messages
    
            HELP_POPUP_RECT = pygame.Rect(popup_x, popup_y, popup_width, popup_height)  # <-- set global
    
            pygame.draw.rect(screen, (40, 40, 40), HELP_POPUP_RECT)
            pygame.draw.rect(screen, (255, 255, 255), HELP_POPUP_RECT, 2)
    
            help_text_lines = [
                "HOW TO PLAY",
                "Turn the Start hexagram into the Goal hexagram using Change Cards.",
                "You have 10 change slots per round. OPTIMAL is the shortest change-path.",
                "POSSIBLE means you still have a chance. After a successful round, the Goal",
                "hexagram will be added to your Hexadeck, and you will be awarded Insight",
                "Points (IP) based on how well you did.",
                "You can use IP to buy Hints or Change Cards. Hints tell you which Change",
                "Card to play next from your available deck, but they reduce the IP you earn.",
                "Change Cards cost more, but they allow for better and shorter change-paths.",
                "Use Coins to advance rounds. The game is over when you either fail to reach",
                "the Goal or when you've filled out your Hexadeck with all 64 hexagrams.",
                "",
                "HOW TO READ A HEXAGRAM",
                "A hexagram is a series of six lines, generated randomly by coin flip. Each",
                "line is either broken (yin) or unbroken (yang). The lines are numbered from",
                "bottom to top.",
                "                                                    6 ----- yang",
                "                                                    5 -- -- yin",
                "                                                    4 ----- yang",
                "                                                    3 -- -- yin",
                "                                                    2 ----- yang",
                "                                                    1 ----- yang",
                "Lines 1-3 are the Lower (▼) trigram. Lines 4-6 are the Upper (▲) trigram.",
                "Some Change Cards act on all lines (purple). Others act only on ▼ (green)",
                "or ▲ (blue). Hover over the Change Cards to see what they do."
            ]
    
            HEADINGS = {"HOW TO PLAY", "HOW TO READ A HEXAGRAM"}
    
            line_y = popup_y + 10
            left_x = popup_x + 50
            LINE_STEP = 19  # keep your original spacing
    
            for line in help_text_lines:
                is_heading = line in HEADINGS
    
    
                surf = render_surf(font, line, (255, 255, 255))
    
                if is_heading:
                    # center horizontally in the popup; keep same y position
                    rect = surf.get_rect(centerx=HELP_POPUP_RECT.centerx, y=line_y)
                else:
                    # left-aligned like before
                    rect = surf.get_rect(topleft=(left_x, line_y))
    
                screen.blit(surf, rect)
                line_y += LINE_STEP
    
        if hover_text and hover_rect:
            draw_tooltip(screen, hover_text, hover_rect, font, prefer_above=True)
        
        pygame.display.flip()    
        await asyncio.sleep(0)

    try:
        import sys
        if sys.platform != "emscripten" and not getattr(sys, "_emscripten_info", None):
            pygame.quit()
    except Exception:
        pass
    return  # no sys.exit() needed

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_game())