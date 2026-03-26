"""Generate architecture diagram as PNG using Pillow."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1600, 1100
img = Image.new("RGB", (W, H), "#f8f9fa")
draw = ImageDraw.Draw(img)

# Try to load a decent font
def get_font(size):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    ]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def get_bold_font(size):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return get_font(size)

font_title = get_bold_font(28)
font_heading = get_bold_font(16)
font_body = get_font(14)
font_small = get_font(12)
font_label = get_bold_font(12)

def draw_box(x, y, w, h, fill, outline, text, subtitle=None):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=10, fill=fill, outline=outline, width=2)
    bbox = draw.textbbox((0, 0), text, font=font_heading)
    tw = bbox[2] - bbox[0]
    ty = y + 10 if subtitle else y + (h - 18) // 2
    draw.text((x + (w - tw) // 2, ty), text, fill=outline, font=font_heading)
    if subtitle:
        for i, line in enumerate(subtitle.split("\n")):
            bbox2 = draw.textbbox((0, 0), line, font=font_small)
            tw2 = bbox2[2] - bbox2[0]
            draw.text((x + (w - tw2) // 2, ty + 22 + i * 16), line, fill="#555", font=font_small)

def draw_arrow(x1, y1, x2, y2, color="#333", label=None, dashed=False):
    if dashed:
        # Draw dashed line
        dx = x2 - x1
        dy = y2 - y1
        length = (dx**2 + dy**2) ** 0.5
        dashes = int(length / 10)
        for i in range(0, dashes, 2):
            t1 = i / dashes
            t2 = min((i + 1) / dashes, 1)
            draw.line(
                [x1 + dx * t1, y1 + dy * t1, x1 + dx * t2, y1 + dy * t2],
                fill=color, width=2
            )
    else:
        draw.line([x1, y1, x2, y2], fill=color, width=2)
    # Arrowhead
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    arrow_len = 10
    draw.polygon([
        (x2, y2),
        (x2 - arrow_len * math.cos(angle - 0.4), y2 - arrow_len * math.sin(angle - 0.4)),
        (x2 - arrow_len * math.cos(angle + 0.4), y2 - arrow_len * math.sin(angle + 0.4)),
    ], fill=color)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        bbox = draw.textbbox((0, 0), label, font=font_label)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        draw.rectangle([mx - lw//2 - 3, my - lh//2 - 2, mx + lw//2 + 3, my + lh//2 + 2], fill="#f8f9fa")
        draw.text((mx - lw // 2, my - lh // 2), label, fill=color, font=font_label)

def draw_zone(x, y, w, h, fill, outline, label):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=12, fill=fill, outline=outline, width=1)
    draw.text((x + 10, y + 5), label, fill=outline, font=font_small)

# ── Title ──
bbox = draw.textbbox((0, 0), "Microservices Architecture", font=font_title)
tw = bbox[2] - bbox[0]
draw.text(((W - tw) // 2, 15), "Microservices Architecture", fill="#1e1e1e", font=font_title)
bbox2 = draw.textbbox((0, 0), "Chat Application — System Design", font=font_body)
tw2 = bbox2[2] - bbox2[0]
draw.text(((W - tw2) // 2, 48), "Chat Application — System Design", fill="#888", font=font_body)

# ── Row 1: Client ──
draw_zone(400, 75, 800, 65, "#e8edff", "#4a9eed", "CLIENT")
draw_box(420, 85, 140, 45, "#cfe2ff", "#4a9eed", "Browser")
draw_box(600, 85, 140, 45, "#cfe2ff", "#4a9eed", "WebSocket")
draw_box(780, 85, 140, 45, "#cfe2ff", "#4a9eed", "REST")

# ── Arrow: Client → Kong ──
draw_arrow(800, 140, 800, 165, "#333")

# ── Row 2: Kong ──
draw_box(350, 165, 900, 50, "#e8daff", "#8b5cf6",
         "Kong Gateway  —  Rate Limiting / CORS / Routing / Request ID")

# ── Arrows: Kong → Services ──
draw_arrow(550, 215, 270, 270, "#d97706", label="/auth")
draw_arrow(680, 215, 600, 270, "#2563eb", label="/ws /rooms")
draw_arrow(900, 215, 950, 270, "#16a34a", label="/messages")
draw_arrow(1050, 215, 1300, 270, "#7c3aed", label="/files")

# ── Row 3: Services ──
draw_zone(40, 260, 1520, 200, "#e6f9e6", "#22c55e", "SERVICES (Docker Network)")

draw_box(60, 285, 300, 160, "#ffe8c8", "#d97706",
         "Auth Service", "Python/FastAPI :8001\nRegister | Login | Logout\nJWT Generation\nUser Lookup (internal)")

draw_box(400, 285, 300, 160, "#cfe2ff", "#2563eb",
         "Chat Service", "Go/Gorilla :8003\nWebSocket Manager | Rooms\nRate Limit 30msg/10s\nCircuit Breaker")

draw_box(740, 285, 300, 160, "#c8f7c8", "#16a34a",
         "Message Service", "Python/FastAPI :8004\nKafka Consumer (WRITE)\nREST History (READ)\nIdempotent Writes (UUID)")

draw_box(1080, 285, 300, 160, "#f0deff", "#7c3aed",
         "File Service", "TypeScript/Express :8005\nMulter Upload (150MB)\nFile Metadata\nDisk Storage")

# ── Service-to-service arrows ──
draw_arrow(400, 370, 360, 370, "#dc2626", label="verify user", dashed=True)
draw_arrow(740, 390, 360, 390, "#dc2626", label="resolve username", dashed=True)

# ── Row 4: Redis + Kafka + Disk ──
# Redis
draw_box(60, 510, 200, 70, "#ffe0e0", "#dc2626",
         "Redis", "JWT Blacklist (logout)")

# Kafka zone
draw_zone(300, 495, 800, 155, "#fff8e0", "#d97706", "KAFKA EVENT BUS")

draw_box(320, 525, 155, 42, "#fff3bf", "#d97706", "chat.messages")
draw_box(495, 525, 145, 42, "#fff3bf", "#d97706", "chat.private")
draw_box(660, 525, 145, 42, "#fff3bf", "#d97706", "file.events")
draw_box(825, 525, 135, 42, "#fff3bf", "#d97706", "auth.events")
draw_box(320, 590, 155, 42, "#ffe0e0", "#dc2626", "chat.dlq")
draw.text((495, 600), "(failed after 3 retries)", fill="#888", font=font_small)

# Disk
draw_box(1140, 510, 200, 70, "#ffe8c8", "#d97706",
         "Disk Storage", "/app/uploads")

# ── PRODUCE arrows (services → kafka) ──
draw_arrow(550, 445, 398, 525, "#d97706", label="PRODUCE")
draw_arrow(550, 445, 568, 525, "#d97706")
draw_arrow(1230, 445, 733, 525, "#d97706", label="PRODUCE")
draw_arrow(210, 445, 893, 525, "#d97706", label="PRODUCE")

# ── CONSUME arrows (kafka → services) ──
draw_arrow(398, 567, 890, 445, "#16a34a", label="CONSUME")
draw_arrow(568, 567, 890, 445, "#16a34a")
draw_arrow(733, 567, 550, 445, "#2563eb", label="CONSUME")

# ── DLQ arrow ──
draw_arrow(890, 445, 398, 610, "#dc2626", label="DLQ", dashed=True)

# ── Auth → Redis ──
draw_arrow(160, 445, 160, 510, "#dc2626")

# ── File → Disk ──
draw_arrow(1230, 445, 1240, 510, "#d97706")

# ── Row 5: Databases ──
draw_zone(100, 700, 1400, 100, "#e0f5f0", "#0d9488",
          "POSTGRESQL  —  Each service owns its DB  (no cross-service foreign keys)")

draw_box(120, 725, 280, 60, "#d0f0e8", "#0d9488",
         "chatbox_auth", "users table")
draw_box(430, 725, 280, 60, "#d0f0e8", "#0d9488",
         "chatbox_chat", "rooms | admins | mutes")
draw_box(740, 725, 280, 60, "#d0f0e8",  "#0d9488",
         "chatbox_messages", "messages (UUID idempotent)")
draw_box(1050, 725, 280, 60, "#d0f0e8", "#0d9488",
         "chatbox_files", "file metadata")

# ── Services → DBs ──
draw_arrow(210, 445, 260, 725, "#0d9488")
draw_arrow(550, 445, 570, 725, "#0d9488")
draw_arrow(890, 445, 880, 725, "#0d9488")
draw_arrow(1230, 445, 1190, 725, "#0d9488")

# ── Legend ──
draw.text((60, 840), "LEGEND:", fill="#333", font=font_heading)
draw.line([60, 870, 110, 870], fill="#d97706", width=2)
draw.text((120, 863), "PRODUCE (async fire-and-forget)", fill="#555", font=font_small)
draw.line([60, 895, 110, 895], fill="#16a34a", width=2)
draw.text((120, 888), "CONSUME (async persistence)", fill="#555", font=font_small)
draw.line([60, 920, 110, 920], fill="#dc2626", width=2)
draw.text((120, 913), "Sync HTTP call / DLQ", fill="#555", font=font_small)
draw.line([60, 945, 110, 945], fill="#0d9488", width=2)
draw.text((120, 938), "Database ownership", fill="#555", font=font_small)

# Key insight
draw_box(500, 840, 700, 120, "#fff8e0", "#d97706",
         "How Messages Flow:",
         "1. User sends via WebSocket → Chat Service broadcasts INSTANTLY\n"
         "2. Chat Service → PRODUCE to Kafka (async)\n"
         "3. Message Service → CONSUME and persist to DB\n"
         "4. On reconnect → GET /messages/history from Message Service")

# Save
output_path = "/home/ido/Desktop/Chat-Project-Final/docs/architecture/diagrams/architecture-diagram.png"
img.save(output_path, "PNG", quality=95)
print(f"Saved to {output_path}")
