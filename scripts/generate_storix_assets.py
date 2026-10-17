#!/usr/bin/env python3
"""
Generate high-fidelity, pixel-perfect Storix brand assets from source uploaded logos.
"""
import os
import io
import base64
import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

UPLOAD_LOGO = "/Users/png/.gemini/antigravity/brain/48cd64b8-afb9-4783-b047-599310494447/.user_uploaded/media_1792227869910_2c568592.png"
UPLOAD_ICON = "/Users/png/.gemini/antigravity/brain/48cd64b8-afb9-4783-b047-599310494447/.user_uploaded/media_1792227869919_dce44da8.png"

def make_white_logo(logo_img):
    """
    Convert dark text in Storix logo to crisp white for dark headers / dark theme,
    while preserving the vibrant 3D gradient icon and the cyan 'x' accent.
    """
    arr = np.array(logo_img).copy()
    h, w, _ = arr.shape
    
    # Automatically locate the gap between the icon (left) and wordmark (right)
    # The gap is a column of 0-alpha pixels between 20% and 35% of image width
    alpha = arr[:, :, 3]
    col_counts = (alpha > 5).sum(axis=0)
    
    search_start = int(w * 0.20)
    search_end = int(w * 0.35)
    
    min_col_idx = search_start + int(np.argmin(col_counts[search_start:search_end]))
    split_x = min_col_idx
    print(f"Detected icon/wordmark split at column x={split_x}")
    
    for y in range(h):
        for x in range(split_x, w):
            r, g, b, a = arr[y, x]
            if a > 0:
                # Check if it's the cyan accent on 'x'
                # Accent has high blue (b > 130) and green > 60 with b > r * 2
                is_accent = (b > 130 and g > 60 and int(b) > int(r) * 2)
                if not is_accent:
                    # Dark navy letter: turn into pure white, maintaining alpha
                    arr[y, x, 0] = 255
                    arr[y, x, 1] = 255
                    arr[y, x, 2] = 255
    return Image.fromarray(arr, "RGBA")

def crop_with_padding(img, padding_ratio=0.06):
    """
    Crop transparent borders and add a clean, balanced padding.
    """
    arr = np.array(img)
    alpha = arr[:, :, 3]
    y_idx = np.where((alpha > 5).any(axis=1))[0]
    x_idx = np.where((alpha > 5).any(axis=0))[0]
    if len(y_idx) == 0 or len(x_idx) == 0:
        return img
    
    min_x, max_x = x_idx[0], x_idx[-1] + 1
    min_y, max_y = y_idx[0], y_idx[-1] + 1
    
    cropped = img.crop((min_x, min_y, max_x, max_y))
    cw, ch = cropped.size
    
    pad_x = int(cw * padding_ratio)
    pad_y = int(ch * padding_ratio)
    
    new_w = cw + pad_x * 2
    new_h = ch + pad_y * 2
    
    canvas = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    canvas.paste(cropped, (pad_x, pad_y), cropped)
    return canvas

def make_square_icon(icon_img, target_size=512):
    """
    Crop icon and center in a target_size x target_size canvas with 8% margin.
    """
    arr = np.array(icon_img)
    alpha = arr[:, :, 3]
    y_idx = np.where((alpha > 5).any(axis=1))[0]
    x_idx = np.where((alpha > 5).any(axis=0))[0]
    
    cropped = icon_img.crop((x_idx[0], y_idx[0], x_idx[-1] + 1, y_idx[-1] + 1))
    cw, ch = cropped.size
    
    # Scale so largest dimension is 86% of target_size
    max_dim = int(target_size * 0.86)
    scale = max_dim / max(cw, ch)
    new_w = int(cw * scale)
    new_h = int(ch * scale)
    
    resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    canvas = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    pos_x = (target_size - new_w) // 2
    pos_y = (target_size - new_h) // 2
    canvas.paste(resized, (pos_x, pos_y), resized)
    return canvas

def create_svg_from_png(png_img, width=512, height=512):
    """
    Create an SVG containing the embedded high-res PNG image.
    """
    buf = io.BytesIO()
    png_img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <image width="{width}" height="{height}" href="data:image/png;base64,{b64_str}"/>
</svg>'''
    return svg_content

def main():
    print(f"Loading source logo from: {UPLOAD_LOGO}")
    raw_logo = Image.open(UPLOAD_LOGO)
    print(f"Loading source icon from: {UPLOAD_ICON}")
    raw_icon = Image.open(UPLOAD_ICON)
    
    # 1. Process Logo
    logo_dark = crop_with_padding(raw_logo, padding_ratio=0.04)
    logo_white = make_white_logo(logo_dark)
    
    # 2. Process Icon
    icon_512 = make_square_icon(raw_icon, target_size=512)
    icon_256 = icon_512.resize((256, 256), Image.Resampling.LANCZOS)
    icon_192 = icon_512.resize((192, 192), Image.Resampling.LANCZOS)
    icon_64 = icon_512.resize((64, 64), Image.Resampling.LANCZOS)
    icon_48 = icon_512.resize((48, 48), Image.Resampling.LANCZOS)
    icon_32 = icon_512.resize((32, 32), Image.Resampling.LANCZOS)
    icon_16 = icon_512.resize((16, 16), Image.Resampling.LANCZOS)
    
    # Generate Multi-size Favicon ICO
    ico_buf = io.BytesIO()
    icon_512.save(ico_buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    ico_bytes = ico_buf.getvalue()
    
    # SVGs
    favicon_svg = create_svg_from_png(icon_512, 512, 512)
    logo_svg = create_svg_from_png(icon_512, 512, 512)
    logo_wide_svg = create_svg_from_png(logo_dark, logo_dark.width, logo_dark.height)
    
    # Target distribution directories
    dest_dirs = [
        os.path.join(PROJECT_ROOT, "console", "public"),
        os.path.join(PROJECT_ROOT, "console", "src", "assets"),
        os.path.join(PROJECT_ROOT, "runtime", "themes", "storix", "core", "img"),
        os.path.join(PROJECT_ROOT, "docs", "images"),
        os.path.join(PROJECT_ROOT, "infra", "docs", "images"),
        os.path.join(PROJECT_ROOT, "runtime", "docs", "images"),
    ]
    
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        print(f"Deploying assets to: {d}")
        
        # Save logos
        logo_dark.save(os.path.join(d, "storix-logo.png"))
        logo_white.save(os.path.join(d, "storix-logo-white.png"))
        icon_512.save(os.path.join(d, "storix-icon.png"))
        
        # Save favicons if appropriate
        icon_32.save(os.path.join(d, "favicon.png"))
        with open(os.path.join(d, "favicon.ico"), "wb") as f:
            f.write(ico_bytes)
            
        if "console/public" in d:
            with open(os.path.join(d, "favicon.svg"), "w") as f:
                f.write(favicon_svg)
                
        if "themes/storix" in d:
            # Nextcloud theme file naming conventions
            logo_dark.save(os.path.join(d, "logo-wide.png"))
            logo_white.save(os.path.join(d, "logo-white.png"))
            icon_512.save(os.path.join(d, "logo.png"))
            icon_32.save(os.path.join(d, "favicon.png"))
            with open(os.path.join(d, "favicon.ico"), "wb") as f:
                f.write(ico_bytes)
            with open(os.path.join(d, "logo.svg"), "w") as f:
                f.write(logo_svg)
            with open(os.path.join(d, "logo-wide.svg"), "w") as f:
                f.write(logo_wide_svg)

    print("✅ All Storix brand assets successfully regenerated and synchronized!")

if __name__ == "__main__":
    main()
