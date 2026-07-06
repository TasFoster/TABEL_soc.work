"""Синтетика «матричного» номера билета — имитирует ВИД ПОСЛЕ предобработки
(увеличение + бинаризация + «склейка» точек): грубые жирные цифры с неровными
краями, шумом, разной толщиной/контрастом. На таких учим распознаватель."""
import random
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

H = 40
DIGITS = "0123456789"
_FONTS = []
def _fonts():
    global _FONTS
    if _FONTS: return _FONTS
    import glob, os
    cands = glob.glob(r"C:\Windows\Fonts\*.ttf")
    pick = [c for c in cands if os.path.basename(c).lower() in
            ("arialbd.ttf","arial.ttf","cour.ttf","courbd.ttf","consola.ttf","consolab.ttf",
             "verdanab.ttf","tahomabd.ttf","framd.ttf","impact.ttf")]
    _FONTS = pick or cands[:6]
    return _FONTS

def render(s, h=H):
    fp = random.choice(_fonts())
    fs = random.randint(int(h*0.8), int(h*1.05))
    font = ImageFont.truetype(fp, fs)
    sp = random.randint(1, 7)
    widths = []
    for ch in s:
        bb = font.getbbox(ch); widths.append(bb[2]-bb[0])
    W = sum(widths) + sp*(len(s)+1) + 10
    img = Image.new("L", (W, h), 255)
    d = ImageDraw.Draw(img)
    x = sp+4
    for ch in s:
        bb = font.getbbox(ch)
        d.text((x-bb[0], (h-(bb[3]-bb[1]))//2 - bb[1]), ch, fill=0, font=font)
        x += (bb[2]-bb[0]) + sp
    return np.array(img)

def degrade(g):
    a = 255 - g  # ink=white
    k = random.choice([(2,2),(3,3),(3,2),(2,3)])
    if random.random()<0.55:
        a = cv2.dilate(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,k))
    if random.random()<0.5:
        a = cv2.erode(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,random.choice([(2,2),(3,2)])))
    # «дырки»/разрывы матричной печати
    if random.random()<0.8:
        holes = (np.random.rand(*a.shape) < random.uniform(0.03,0.14)).astype(np.uint8)*255
        a = cv2.subtract(a, cv2.bitwise_and(holes, a))
    # пятна-шум вокруг
    if random.random()<0.6:
        spk = (np.random.rand(*a.shape) < random.uniform(0.01,0.06)).astype(np.uint8)*255
        a = cv2.bitwise_or(a, cv2.dilate(spk, np.ones((2,2),np.uint8)))
    ang = random.uniform(-6,6); Hh,Ww=a.shape
    M = cv2.getRotationMatrix2D((Ww/2,Hh/2), ang, 1.0)
    a = cv2.warpAffine(a, M, (Ww,Hh), borderValue=0)
    a = cv2.GaussianBlur(a, (3,3), random.uniform(0.4,1.4))
    a = np.clip(a.astype(np.int16) + np.random.normal(0,random.uniform(5,22),a.shape),0,255).astype(np.uint8)
    _,a = cv2.threshold(a, random.randint(55,135), 255, cv2.THRESH_BINARY)
    # «склейка» как в нашем препроцессинге реальных билетов
    a = cv2.morphologyEx(a, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, random.choice([(3,3),(5,3),(7,5)])))
    return 255 - a

def sample():
    n = random.randint(6,7)
    s = "".join(random.choice(DIGITS) for _ in range(n))
    return degrade(render(s)), s

if __name__ == "__main__":
    rows=[]
    for _ in range(12):
        im,s = sample()
        im = cv2.copyMakeBorder(im,2,2,2, max(0,260-im.shape[1]),cv2.BORDER_CONSTANT,value=255)[:,:260]
        rows.append(im)
    cv2.imwrite("neuro/_synth_demo.png", np.vstack(rows))
    print("demo saved")
