from PIL import Image, ImageDraw, ImageFont
import textwrap


WIDTH, HEIGHT = 1800, 2760
OUT = "docs/diagrams/verityflow-primary-user-journey.png"

COLORS = {
    "ink": "#172B4D",
    "muted": "#5E6C84",
    "line": "#8C9AAF",
    "analyst": "#F1E9FF",
    "analyst_border": "#7F5CC4",
    "system": "#E9F2FF",
    "system_border": "#0C66E4",
    "validation": "#E3FCEF",
    "validation_border": "#14804A",
    "moss": "#E7F8EE",
    "moss_border": "#1F845A",
    "review": "#FFF4E5",
    "review_border": "#B65C02",
    "danger": "#FFF0EE",
    "danger_border": "#C9372C",
    "memory": "#F2F0FF",
    "memory_border": "#6554C0",
    "dark": "#13294B",
}

FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


canvas = Image.new("RGB", (WIDTH, HEIGHT), "#FFFFFF")
draw = ImageDraw.Draw(canvas)


def wrapped_lines(text, max_chars):
    lines = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=max_chars) or [""])
    return lines


def centered_text(box, text, size=31, color=COLORS["ink"], bold=True, max_chars=34):
    x1, y1, x2, y2 = box
    lines = wrapped_lines(text, max_chars)
    fnt = font(size, bold)
    spacing = int(size * 0.34)
    heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=fnt)
        heights.append(bbox[3] - bbox[1])
    total = sum(heights) + spacing * max(0, len(lines) - 1)
    y = y1 + (y2 - y1 - total) / 2
    for line, line_height in zip(lines, heights):
        bbox = draw.textbbox((0, 0), line, font=fnt)
        line_width = bbox[2] - bbox[0]
        draw.text(((x1 + x2 - line_width) / 2, y), line, fill=color, font=fnt)
        y += line_height + spacing


def rounded_box(x, y, w, h, text, fill, border, size=30, max_chars=34, radius=24):
    box = (x, y, x + w, y + h)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=border, width=4)
    centered_text(box, text, size=size, max_chars=max_chars)
    return box


def diamond(cx, cy, w, h, text, fill, border):
    points = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
    draw.polygon(points, fill=fill, outline=border)
    draw.line(points + [points[0]], fill=border, width=4, joint="curve")
    centered_text((cx - w / 2 + 48, cy - h / 2 + 18, cx + w / 2 - 48, cy + h / 2 - 18), text, size=29, max_chars=23)
    return points


def arrow(start, end, color=COLORS["line"], width=5, dashed=False):
    x1, y1 = start
    x2, y2 = end
    if dashed:
        segments = 12
        for i in range(0, segments, 2):
            ax = x1 + (x2 - x1) * i / segments
            ay = y1 + (y2 - y1) * i / segments
            bx = x1 + (x2 - x1) * (i + 1) / segments
            by = y1 + (y2 - y1) * (i + 1) / segments
            draw.line((ax, ay, bx, by), fill=color, width=width)
    else:
        draw.line((x1, y1, x2, y2), fill=color, width=width)
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 18
    wing = 0.58
    p1 = (x2 - length * math.cos(angle - wing), y2 - length * math.sin(angle - wing))
    p2 = (x2 - length * math.cos(angle + wing), y2 - length * math.sin(angle + wing))
    draw.polygon([(x2, y2), p1, p2], fill=color)


def poly_arrow(points, color=COLORS["line"], width=5, dashed=False):
    for index in range(len(points) - 1):
        last = index == len(points) - 2
        if last:
            arrow(points[index], points[index + 1], color=color, width=width, dashed=dashed)
        else:
            draw.line((*points[index], *points[index + 1]), fill=color, width=width)


def label(x, y, text, fill="#FFFFFF", color=COLORS["muted"]):
    fnt = font(24, True)
    bbox = draw.textbbox((0, 0), text, font=fnt)
    pad_x, pad_y = 14, 7
    box = (x, y, x + bbox[2] - bbox[0] + pad_x * 2, y + bbox[3] - bbox[1] + pad_y * 2)
    draw.rounded_rectangle(box, radius=13, fill=fill)
    draw.text((x + pad_x, y + pad_y - 2), text, font=fnt, fill=color)


# Header
draw.text((100, 66), "VerityFlow Primary User Journey", font=font(54, True), fill=COLORS["ink"])
draw.text(
    (100, 137),
    "From validated operational data to an approved, context-grounded report",
    font=font(27),
    fill=COLORS["muted"],
)
draw.line((100, 195, WIDTH - 100, 195), fill="#DFE5EF", width=3)

# Lane legend
legend = [
    ("Analyst action", COLORS["analyst"], COLORS["analyst_border"]),
    ("VerityFlow", COLORS["system"], COLORS["system_border"]),
    ("Moss retrieval", COLORS["moss"], COLORS["moss_border"]),
    ("Review / decision", COLORS["review"], COLORS["review_border"]),
]
lx = 100
for text, fill, border in legend:
    draw.rounded_rectangle((lx, 224, lx + 30, 254), radius=7, fill=fill, outline=border, width=3)
    draw.text((lx + 42, 224), text, font=font(22, True), fill=COLORS["muted"])
    lx += 360

cx, w, h = 900, 660, 118
x = cx - w // 2

# Main journey
b1 = rounded_box(x, 310, w, h, "Analyst selects customer, site and report configuration", COLORS["analyst"], COLORS["analyst_border"], max_chars=42)
arrow((cx, 428), (cx, 468))
b2 = rounded_box(x, 468, w, h, "Connect Excel or BigQuery data", COLORS["system"], COLORS["system_border"])
arrow((cx, 586), (cx, 626))
b3 = rounded_box(x, 626, w, h, "Validate data quality", COLORS["validation"], COLORS["validation_border"])
arrow((cx, 744), (cx, 780))
d1 = diamond(cx, 875, 500, 165, "Is the data suitable for reporting?", COLORS["review"], COLORS["review_border"])

# Validation correction loop
issue = rounded_box(70, 805, 430, 120, "Show missing, invalid or suspicious data", COLORS["danger"], COLORS["danger_border"], size=27, max_chars=29)
correct = rounded_box(70, 985, 430, 120, "Analyst corrects the source data", COLORS["analyst"], COLORS["analyst_border"], size=27, max_chars=29)
arrow((650, 875), (500, 875), color=COLORS["danger_border"])
label(525, 832, "NO", fill="#FFF0EE", color=COLORS["danger_border"])
arrow((285, 925), (285, 985), color=COLORS["danger_border"])
poly_arrow([(285, 1105), (285, 1160), (530, 1160), (530, 527), (570, 527)], color=COLORS["analyst_border"], width=4, dashed=True)

label(931, 952, "YES", fill="#E3FCEF", color=COLORS["validation_border"])
arrow((cx, 958), (cx, 1000))
b4 = rounded_box(x, 1000, w, h, "Load approved mappings, formulas, rules and questions", COLORS["system"], COLORS["system_border"], max_chars=41)
arrow((cx, 1118), (cx, 1154))
b5 = rounded_box(x, 1154, w, h, "Deterministic engines calculate KPIs and identify findings", COLORS["system"], COLORS["system_border"], max_chars=42)
arrow((cx, 1272), (cx, 1308))
b6 = rounded_box(x, 1308, w, h, "Create evidence packet", COLORS["validation"], COLORS["validation_border"])
arrow((cx, 1426), (cx, 1462))
b7 = rounded_box(x, 1462, w, h, "Moss retrieves relevant approved business context", COLORS["moss"], COLORS["moss_border"], max_chars=41)

# Context memory
memory = rounded_box(1320, 1428, 390, 186, "Approved Context Memory\nKPI definitions · preferences · rules · guidance", COLORS["memory"], COLORS["memory_border"], size=25, max_chars=28)
arrow((1320, 1521), (1230, 1521), color=COLORS["memory_border"])

arrow((cx, 1580), (cx, 1616))
b8 = rounded_box(x, 1616, w, h, "Grounded narrative agent drafts an explanation", COLORS["system"], COLORS["system_border"], max_chars=40)
arrow((cx, 1734), (cx, 1770))
b9 = rounded_box(x, 1770, w, 138, "Review UI shows calculated evidence, retrieved context and proposed narrative", COLORS["review"], COLORS["review_border"], size=28, max_chars=44)
arrow((cx, 1908), (cx, 1942))
d2 = diamond(cx, 2030, 500, 160, "Analyst decision", COLORS["analyst"], COLORS["analyst_border"])

# Edit/reject feedback loop
edit = rounded_box(70, 1970, 420, 116, "Edit the narrative", COLORS["analyst"], COLORS["analyst_border"], size=27)
reject = rounded_box(1310, 1970, 420, 116, "Reject or investigate", COLORS["danger"], COLORS["danger_border"], size=27)
arrow((650, 2030), (490, 2030), color=COLORS["analyst_border"])
label(520, 1988, "EDIT", fill=COLORS["analyst"], color=COLORS["analyst_border"])
arrow((1150, 2030), (1310, 2030), color=COLORS["danger_border"])
label(1170, 1988, "REJECT", fill=COLORS["danger"], color=COLORS["danger_border"])
poly_arrow([(280, 1970), (280, 1840), (570, 1840)], color=COLORS["analyst_border"], width=4, dashed=True)
poly_arrow([(1520, 1970), (1520, 1840), (1230, 1840)], color=COLORS["danger_border"], width=4, dashed=True)

label(931, 2116, "APPROVE", fill="#E3FCEF", color=COLORS["validation_border"])
arrow((cx, 2110), (cx, 2160))
b10 = rounded_box(x, 2160, w, h, "Approve final report", COLORS["analyst"], COLORS["analyst_border"])
arrow((cx, 2278), (cx, 2314))
b11 = rounded_box(x, 2314, w, h, "Create immutable report snapshot and audit trace", COLORS["system"], COLORS["system_border"], max_chars=42)
arrow((cx, 2432), (cx, 2468))
b12 = rounded_box(x, 2468, w, 126, "Customer-ready PDF, portal or email output", COLORS["dark"], COLORS["dark"], size=30, max_chars=38)
centered_text(b12, "Customer-ready PDF, portal or email output", size=30, color="#FFFFFF", max_chars=38)

# Controlled learning loop
poly_arrow([(1230, 2219), (1645, 2219), (1645, 1614)], color=COLORS["memory_border"], width=4, dashed=True)
label(1320, 2162, "Save reusable guidance", fill="#F2F0FF", color=COLORS["memory_border"])

# Footer principle
draw.rounded_rectangle((100, 2660, WIDTH - 100, 2720), radius=18, fill="#F7F9FC")
centered_text(
    (120, 2660, WIDTH - 120, 2720),
    "Facts are calculated deterministically · Context is retrieved from approved memory · Analysts control publication",
    size=23,
    color=COLORS["muted"],
    bold=True,
    max_chars=112,
)

canvas.save(OUT, "PNG", optimize=True)
print(OUT)
