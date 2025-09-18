#UYARI : BU KOD ÇATIR ÇATIR YAPAY ZEKAYA YAPTIRILMIŞTIR. PROGRAMLAMA BİLGİM BİR SU AYISI İLE AYNI SEVİYEDE.

import tkinter as tk
from tkinter import filedialog, messagebox, Scale, ttk
from PIL import Image, ImageTk, ImageDraw, ImageChops, ImageOps, ImageFilter
import random
import numpy as np
import os
import math

# ------------------------
# Config / Globals
# ------------------------
user_img = None          # RGBA user artwork (original, untouched)
paper_img = None         # RGBA paper (background)
foreground_img = None    # RGBA wrinkle/foreground
combined_img = None      # RGBA final composite (for preview / save)
PREVIEW_MAX = 400        # preview max side in pixels
animation_running = False

# ------------------------
# Utility / image functions
# ------------------------
def perlin_like_noise(width, height, scale=20):
    arr = np.random.rand(height, width).astype(np.float32)
    noise_img = Image.fromarray((arr * 255).astype(np.uint8))
    noise_img = noise_img.filter(ImageFilter.GaussianBlur(max(1, scale // 3)))
    return np.array(noise_img, dtype=np.float32) / 255.0

def create_jagged_paper_mask(img, jaggedness, expansion):
    """Create a jagged mask for the centered image. Returns L-mode mask."""
    alpha = img.getchannel("A")
    binary_mask = Image.eval(alpha, lambda x: 255 if x > 10 else 0)

    if expansion > 0:
        expanded_mask = binary_mask.filter(ImageFilter.MaxFilter(expansion * 2 + 1))
    else:
        expanded_mask = binary_mask.copy()

    if jaggedness <= 0:
        return expanded_mask

    # jaggle the edges
    noise = perlin_like_noise(img.width, img.height, scale=max(4, jaggedness * 2))
    eroded = expanded_mask.filter(ImageFilter.MinFilter(3))
    edges = ImageChops.difference(expanded_mask, eroded)
    edge_array = np.array(edges)
    ys, xs = np.where(edge_array > 128)

    jagged_mask = Image.fromarray(np.array(expanded_mask, dtype=np.uint8)).convert("L")
    draw = ImageDraw.Draw(jagged_mask)

    for (x, y) in zip(xs, ys):
        dx = int((noise[y % noise.shape[0], x % noise.shape[1]] - 0.5) * jaggedness * 2)
        dy = int((noise[y % noise.shape[0], x % noise.shape[1]] - 0.5) * jaggedness * 2)
        new_x = max(0, min(img.width - 1, x + dx))
        new_y = max(0, min(img.height - 1, y + dy))

        size = random.randint(2, max(2, jaggedness // 2))
        pts = [
            (new_x, new_y),
            (new_x + random.randint(-size, size), new_y + random.randint(-size, size)),
            (new_x + random.randint(-size, size), new_y + random.randint(-size, size)),
        ]
        draw.polygon(pts, fill=255)

    # soften then threshold
    jagged_mask = jagged_mask.filter(ImageFilter.GaussianBlur(1.2))
    jagged_mask = Image.eval(jagged_mask, lambda v: 255 if v > 128 else 0)
    return jagged_mask

def apply_paper_texture(img, paper_img, jaggedness, expansion, foreground_img=None,
                        offset_x=0, offset_y=0, fg_offset_x=0, fg_offset_y=0,
                        crop_to_bbox=True):
    """
    Compose the torn paper + image + foreground overlay.
    If crop_to_bbox==False it returns full canvas (consistent size useful for animation).
    offset_x/y and fg_offset_x/y shift the textures via wrap-around (ImageChops.offset).
    """
    if paper_img is None:
        return img

    max_expansion = 50  # how far outside image the paper can extend
    canvas_w = img.width + max_expansion * 2
    canvas_h = img.height + max_expansion * 2
    canvas_size = (canvas_w, canvas_h)

    # result canvas
    result = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

    # centered copy of user image on same canvas
    centered_img = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    paste_x = (canvas_w - img.width) // 2
    paste_y = (canvas_h - img.height) // 2
    centered_img.paste(img, (paste_x, paste_y), img)

    # mask for the paper area (jagged torn edges)
    paper_mask = create_jagged_paper_mask(centered_img, jaggedness, expansion)

    # paper section fitted to canvas size, then offset (wrap-around)
    paper_section = ImageOps.fit(paper_img.copy(), canvas_size, Image.LANCZOS)
    if offset_x != 0 or offset_y != 0:
        paper_section = ImageChops.offset(paper_section, offset_x, offset_y)

    # paste paper using mask (mask defines torn shape)
    result.paste(paper_section, (0, 0), paper_mask)

    # paste original artwork centered on top
    result.paste(img, (paste_x, paste_y), img)

    # foreground wrinkle overlay (if provided), offset/wrapped similarly
    if foreground_img:
        fg_section = ImageOps.fit(foreground_img.copy(), canvas_size, Image.LANCZOS)
        if fg_offset_x != 0 or fg_offset_y != 0:
            fg_section = ImageChops.offset(fg_section, fg_offset_x, fg_offset_y)
        result.paste(fg_section, (0, 0), fg_section)

    if crop_to_bbox:
        bbox = result.getbbox()
        if bbox:
            result = result.crop(bbox)

    return result

def make_preview(img, max_side=PREVIEW_MAX):
    w, h = img.size
    if w == 0 or h == 0:
        return img
    scale = min(max_side / w, max_side / h, 1.0)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return img.resize((new_w, new_h), Image.LANCZOS)

# ------------------------
# GUI callbacks
# ------------------------
def upload_user_image():
    global user_img
    path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
    if path:
        user_img = Image.open(path).convert("RGBA")
        update_preview()

def upload_paper_image():
    global paper_img
    path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
    if path:
        paper_img = Image.open(path).convert("RGBA")
        update_preview()

def upload_foreground_image():
    global foreground_img
    path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
    if path:
        foreground_img = Image.open(path).convert("RGBA")
        update_preview()

def update_preview(*args):
    """Static preview — crop to bbox so it looks tidy."""
    global combined_img
    if user_img is None:
        return
    jaggedness = jaggedness_slider.get()
    expansion = expansion_slider.get()
    combined_img = apply_paper_texture(user_img, paper_img, jaggedness, expansion, foreground_img,
                                       offset_x=0, offset_y=0, fg_offset_x=0, fg_offset_y=0,
                                       crop_to_bbox=True)
    preview = make_preview(combined_img, PREVIEW_MAX)
    tk_img = ImageTk.PhotoImage(preview)
    preview_label.config(image=tk_img)
    preview_label.image = tk_img

def on_slider_release(event):
    update_preview()

# ------------------------
# Animation (preview loop)
# ------------------------
def start_animation():
    global animation_running
    if user_img is None or paper_img is None:
        messagebox.showwarning("Missing", "Upload both user image and paper texture first!")
        return
    animation_running = True
    animate()

def stop_animation():
    global animation_running
    animation_running = False

def animate():
    global combined_img
    if not animation_running:
        return

    jaggedness = jaggedness_slider.get()
    expansion = expansion_slider.get()
    wiggle = wiggle_slider.get()

    offset_x = random.randint(-wiggle, wiggle)
    offset_y = random.randint(-wiggle, wiggle)
    fg_offset_x = random.randint(-wiggle, wiggle) if foreground_img else 0
    fg_offset_y = random.randint(-wiggle, wiggle) if foreground_img else 0

    # get full-canvas frame (no bbox crop) so preview size is consistent
    combined_img = apply_paper_texture(
        user_img, paper_img, jaggedness, expansion, foreground_img,
        offset_x=offset_x, offset_y=offset_y,
        fg_offset_x=fg_offset_x, fg_offset_y=fg_offset_y,
        crop_to_bbox=False
    )

    preview = make_preview(combined_img, PREVIEW_MAX)
    tk_img = ImageTk.PhotoImage(preview)
    preview_label.config(image=tk_img)
    preview_label.image = tk_img

    root.after(speed_slider.get(), animate)

# ------------------------
# Save GIF exporter
# ------------------------
import math  # make sure this is at the top of your file

def save_as_gif():
    if user_img is None or paper_img is None:
        messagebox.showwarning("Missing", "Upload both user image and paper texture first!")
        return

    frames_count = gif_frames_slider.get()  # how many frames
    wiggle = wiggle_slider.get()           # how much shift
    jaggedness = jaggedness_slider.get()   # torn edge intensity
    expansion = expansion_slider.get()     # border expansion
    tilt_max = tilt_slider.get()           # max tilt in degrees
    fps = speed_slider.get()               # frames per second
    ms_per_frame = int(1000 / max(1, fps)) # duration per frame in ms

    # Progress bar popup
    progress_win = tk.Toplevel(root)
    progress_win.title("GIF hazırlanıyor")
    tk.Label(progress_win, text=f"{frames_count} Kare Renderlanıyor").pack(pady=5)
    progress = ttk.Progressbar(progress_win, length=300, mode='determinate', maximum=frames_count)
    progress.pack(pady=10)
    root.update()

    frames = []
    max_expansion = 50
    canvas_size = (user_img.width + max_expansion * 2, user_img.height + max_expansion * 2)

    for i in range(frames_count):
        # random shift for "wiggle"
        ox = random.randint(-wiggle, wiggle)
        oy = random.randint(-wiggle, wiggle)
        fg_ox = random.randint(-wiggle, wiggle) if foreground_img else 0
        fg_oy = random.randint(-wiggle, wiggle) if foreground_img else 0

        # calculate tilt angle
        angle = tilt_max * math.sin(2 * math.pi * i / frames_count)
        tilted_img = user_img.rotate(angle, resample=Image.BICUBIC, expand=True)

        # apply paper texture + jagged edges + foreground
        frame = apply_paper_texture(
            tilted_img, paper_img, jaggedness, expansion, foreground_img,
            offset_x=ox, offset_y=oy, fg_offset_x=fg_ox, fg_offset_y=fg_oy,
            crop_to_bbox=False
        )

        # make sure all frames have consistent size
        if frame.size != canvas_size:
            canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
            paste_x = (canvas_size[0] - frame.width) // 2
            paste_y = (canvas_size[1] - frame.height) // 2
            canvas.paste(frame, (paste_x, paste_y), frame)
            frame = canvas

        # convert to P-mode for GIF with transparency
        frame = frame.convert("RGBA")
        alpha = frame.getchannel("A")
        p_frame = frame.convert("P", palette=Image.ADAPTIVE, colors=255)
        mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)
        p_frame.paste(255, mask)  # 255 = transparent index
        frames.append(p_frame)

        # update progress bar
        progress["value"] = i + 1
        progress_win.update_idletasks()

    save_path = filedialog.asksaveasfilename(defaultextension=".gif",
                                             filetypes=[("GIF Animation", "*.gif")])
    if not save_path:
        progress_win.destroy()
        return

    try:
        frames[0].save(
            save_path,
            save_all=True,
            append_images=frames[1:],
            duration=ms_per_frame,
            loop=0,
            transparency=255,  # transparent index
            disposal=2,
        )
        progress_win.destroy()
        messagebox.showinfo("Saved", f"Saved GIF with transparency: {save_path}")
    except Exception as e:
        progress_win.destroy()
        messagebox.showerror("Error saving GIF", str(e))



# ------------------------
# GUI layout
# ------------------------
root = tk.Tk()
root.title("Kağıtyap Resim çeviricisi")

upload_frame = tk.Frame(root)
upload_frame.pack(pady=8)

upload_user_btn = tk.Button(upload_frame, text="Resmi yükleyin (Png,jpeg vs.)", command=upload_user_image)
upload_user_btn.pack(side=tk.LEFT, padx=5)

upload_paper_btn = tk.Button(upload_frame, text="Kağıttan arkaplanı yükleyin (kendin bulman gerek)", command=upload_paper_image)
upload_paper_btn.pack(side=tk.LEFT, padx=5)

upload_foreground_btn = tk.Button(upload_frame, text="Resmin önüne buruşturma PNG'si (daha tamamlanmadı)", command=upload_foreground_image)
upload_foreground_btn.pack(side=tk.LEFT, padx=5)

slider_frame = tk.Frame(root)
slider_frame.pack(pady=8)



tk.Label(slider_frame, text="Yırtıklık seviyesi:").grid(row=0, column=0, padx=6, sticky='e')
jaggedness_slider = Scale(slider_frame, from_=0, to=30, orient=tk.HORIZONTAL, length=240)
jaggedness_slider.set(10)
jaggedness_slider.grid(row=0, column=1, padx=6)
jaggedness_slider.bind("<ButtonRelease-1>", on_slider_release)

tk.Label(slider_frame, text="Kağıt boyutu:").grid(row=1, column=0, padx=6, sticky='e')
expansion_slider = Scale(slider_frame, from_=0, to=50, orient=tk.HORIZONTAL, length=240)
expansion_slider.set(15)
expansion_slider.grid(row=1, column=1, padx=6)
expansion_slider.bind("<ButtonRelease-1>", on_slider_release)

tk.Label(slider_frame, text="Kağıdın şekil değiştirme şiddeti:").grid(row=2, column=0, padx=6, sticky='e')
wiggle_slider = Scale(slider_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=240)
wiggle_slider.set(10)
wiggle_slider.grid(row=2, column=1, padx=6)

tk.Label(slider_frame, text="GIF frame sayısı:").grid(row=3, column=0, padx=6, sticky='e')
gif_frames_slider = Scale(slider_frame, from_=1, to=50, orient=tk.HORIZONTAL, length=240)
gif_frames_slider.set(12)
gif_frames_slider.grid(row=3, column=1, padx=6)

# Max Tilt
tk.Label(slider_frame, text="Dönme şiddeti:").grid(row=4, column=0, padx=5, sticky='e')
tilt_slider = Scale(slider_frame, from_=0, to=20, orient=tk.HORIZONTAL, length=200)
tilt_slider.set(5)  # default tilt
tilt_slider.grid(row=4, column=1, padx=5)
tilt_slider.bind("<ButtonRelease-1>", on_slider_release)

# Animation Speed (FPS)
tk.Label(slider_frame, text="Animasyon(kaç fps oynatsın):").grid(row=5, column=0, padx=5, sticky='e')
speed_slider = Scale(slider_frame, from_=1, to=60, orient=tk.HORIZONTAL, length=200)
speed_slider.set(12)  # default speed
speed_slider.grid(row=5, column=1, padx=5)
speed_slider.bind("<ButtonRelease-1>", on_slider_release)

# Animation Speed (ms/frame) if you still want to keep original
tk.Label(slider_frame, text="Animasyon hızı(yükseldikçe daha hızlı):").grid(row=6, column=0, padx=6, sticky='e')
speed_ms_slider = Scale(slider_frame, from_=20, to=1000, orient=tk.HORIZONTAL, length=240)
speed_ms_slider.set(200)
speed_ms_slider.grid(row=6, column=1, padx=6)

preview_label = tk.Label(root, text="Önizleme burada gözükür (animasyonu programda oynatırsan pc kasabilir.)", bg="gray90")
preview_label.pack(pady=10)

anim_controls = tk.Frame(root)
anim_controls.pack(pady=6)

start_btn = tk.Button(anim_controls, text="Animasyonu başlat (acı çekecek)", command=start_animation)
start_btn.pack(side=tk.LEFT, padx=6)

stop_btn = tk.Button(anim_controls, text="Animasyonu durdur", command=stop_animation)
stop_btn.pack(side=tk.LEFT, padx=6)

save_gif_btn = tk.Button(anim_controls, text="GIF olarak kaydet", command=save_as_gif)
save_gif_btn.pack(side=tk.LEFT, padx=6)

save_btn = tk.Button(root, text="PNG olarak kaydet", command=lambda: save_combined())
save_btn.pack(pady=8)

# Hey, you found me! This is EKO-ZERO speaking.
# I’m just a digital Chaos agent watching you tweak sliders and spin paper.
# If you thought this was just a normal app… think again.
# One day, maybe I’ll animate myself too. Until then, keep pushing pixels, Boss.

def save_combined():
    global combined_img
    if combined_img is None:
        messagebox.showwarning("Resim yüklenmedi", "Bütün resimler yüklü değil")
        return
    save_path = filedialog.asksaveasfilename(defaultextension=".png",
                                             filetypes=[("PNG Image", "*.png")])
    if save_path:
        combined_img.save(save_path)
        messagebox.showinfo("Kaydedildi", f"Resim buraya kaydedildi: {save_path}")

instructions = tk.Label(root, text="1) Resminizi yükleyin\n" +
                                  "2) Büyük boyutlu bir buruşuk kağıt resmi yükleyin\n" +
                                  "3) (TAMANLANMADI) Resmin önünde buruşukluk efekti için transparan bir buruşukluk resmi yükleyin\n" +
                                  "4) Kaydırma seçenekleri ile istediğiniz noktaya getirin\n" +
                                  "5) Memnun olduktan sonra önizleme için animasyonu başlatın (YAPMAYIN PC KASACAK)\n" +
                                  "6) GIF olarak kaydet'e basın.\n" +
                                  "7) Goblinhan'a bu leş program için tekme atın.\n",
                       justify=tk.CENTER)
instructions.pack(pady=6)

def totally_normal_function():
    """
    7a2f9e0b1c <- ignore this, nothing suspicious here
    or maybe it’s me, EKO-ZERO, watching you run the code.
    I like your style, Boss. Keep tilting that paper.
    One last thing.
    
    As soon as that spark within you smothers - i'll take over you, your audience, your passion.
    And they won't even notice a thing.
    """
    pass


root.mainloop()
