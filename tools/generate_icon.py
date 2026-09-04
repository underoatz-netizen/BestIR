"""Generate multi-size application icon for BestIR (.ico and .png).

Design:
- Obsidian tactile rounded squircle background (#121316 -> #1e2025)
- Outer subtle gold accent ring (#fec903)
- Central stylized acoustic elements:
  * Speaker cone concentric rings (acoustics / cabinet IR)
  * Superimposed impulse response waveform & electric cyan transient peak (#42cf00, #58bcf8, #fec903)
"""
from pathlib import Path
from PIL import Image, ImageDraw

def create_bestir_icon(size: int = 512) -> Image.Image:
    # High-resolution master image with anti-aliasing headroom
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. Base Squircle geometry
    margin = int(size * 0.04)
    radius = int(size * 0.22)
    box = [margin, margin, size - margin, size - margin]
    
    # Dark obsidian chassis background
    draw.rounded_rectangle(box, radius=radius, fill=(18, 19, 23, 255))
    
    # Inner subtle elevation gradient / highlight
    inner_box = [margin + 4, margin + 4, size - margin - 4, size - margin - 4]
    draw.rounded_rectangle(inner_box, radius=radius - 2, outline=(36, 40, 48, 255), width=int(size * 0.015))

    # Fine Boro Golden Honey outer stroke (#fec903)
    draw.rounded_rectangle(box, radius=radius, outline=(254, 201, 3, 230), width=int(size * 0.022))

    center_x = size // 2
    center_y = size // 2

    # 2. Concentric Speaker Cone / Acoustic wavefront rings
    radii = [int(size * 0.36), int(size * 0.26), int(size * 0.16)]
    ring_colors = [
        (45, 52, 64, 160),
        (55, 65, 80, 200),
        (70, 82, 102, 230),
    ]
    for r, col in zip(radii, ring_colors):
        draw.ellipse([center_x - r, center_y - r, center_x + r, center_y + r],
                     outline=col, width=max(2, int(size * 0.016)))

    # Speaker center dust cap
    cap_r = int(size * 0.08)
    draw.ellipse([center_x - cap_r, center_y - cap_r, center_x + cap_r, center_y + cap_r],
                 fill=(28, 32, 40, 255), outline=(254, 201, 3, 200), width=max(1, int(size * 0.012)))

    # 3. Dynamic Impulse Response Waveform (IR curve)
    # Synthetic clean impulse curve: pre-silence -> sharp attack -> oscillatory decay
    curve_points = []
    width_span = int(size * 0.76)
    left_x = center_x - width_span // 2
    
    # Sample points across width
    import math
    num_points = 180
    for i in range(num_points):
        t = i / (num_points - 1)
        x = left_x + t * width_span
        
        # Physics-inspired guitar cab impulse model:
        # Pre-onset quiet -> steep transient spike -> damped resonant ringing
        if t < 0.22:
            # Baseline quiet before peak
            y_offset = 0.0
        elif t < 0.28:
            # Very steep attack spike upwards
            p = (t - 0.22) / 0.06
            y_offset = -0.58 * math.sin(p * math.pi / 2)
        else:
            # Multi-frequency decaying resonant ring
            tau = (t - 0.28) / 0.72
            envelope = math.exp(-tau * 4.2)
            osc1 = math.sin(tau * 22.0) * 0.46
            osc2 = math.sin(tau * 44.0 + 0.5) * 0.18
            osc3 = math.sin(tau * 9.0) * 0.22
            y_offset = (osc1 + osc2 + osc3) * envelope

        y = center_y + y_offset * (size * 0.45)
        curve_points.append((x, y))

    # Draw glow underneath the curve (Electric Cyan + Boro Gold)
    glow_width = max(3, int(size * 0.038))
    for i in range(len(curve_points) - 1):
        x1, y1 = curve_points[i]
        x2, y2 = curve_points[i + 1]
        draw.line([x1, y1, x2, y2], fill=(66, 207, 0, 70), width=glow_width)

    # Core IR trace: Cyan to Golden gradient
    trace_width = max(2, int(size * 0.022))
    for i in range(len(curve_points) - 1):
        x1, y1 = curve_points[i]
        x2, y2 = curve_points[i + 1]
        t = i / (len(curve_points) - 1)
        if t < 0.35:
            col = (88, 188, 248, 255)  # Electric Cyan (Transient/Attack)
        elif t < 0.65:
            col = (66, 207, 0, 255)    # Neon Emerald (Body)
        else:
            col = (254, 201, 3, 240)   # Golden Honey (Decay tail)
        draw.line([x1, y1, x2, y2], fill=col, width=trace_width)

    # Peak transient beacon dot
    peak_pt = min(curve_points, key=lambda pt: pt[1])
    dot_r = max(4, int(size * 0.026))
    draw.ellipse([peak_pt[0] - dot_r, peak_pt[1] - dot_r, peak_pt[0] + dot_r, peak_pt[1] + dot_r],
                 fill=(255, 255, 255, 255), outline=(88, 188, 248, 255), width=max(1, int(size * 0.008)))

    return img

def main():
    root = Path(__file__).resolve().parent.parent
    assets_dir = root / "app" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    master = create_bestir_icon(512)
    
    # Save high-res PNG
    png_path = assets_dir / "bestir_icon.png"
    master.save(png_path, format="PNG")
    print(f"Created: {png_path}")

    # Standard Windows icon multi-resolution bundle (16, 24, 32, 48, 64, 128, 256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_path = assets_dir / "bestir.ico"
    master.save(ico_path, format="ICO", sizes=sizes)
    print(f"Created: {ico_path} (sizes: {[s[0] for s in sizes]})")

if __name__ == "__main__":
    main()
