import sys, glob, cv2, numpy as np, torch
sys.path.insert(0,"neuro")
from model import CRNN, IMG_H
def prep(g):
    h,w=g.shape; W=min(200,max(16,int(round(w*IMG_H/h)))); g=cv2.resize(g,(W,IMG_H))
    return torch.from_numpy(255-g).float().div(255).unsqueeze(0).unsqueeze(0)
def decode(logp):
    idx=logp.argmax(2).T.tolist(); out=[]
    for seq in idx:
        s=[];prev=-1
        for k in seq:
            if k!=10 and k!=prev: s.append(str(k))
            prev=k
        out.append("".join(s))
    return out
net=CRNN(); net.load_state_dict(torch.load("neuro/crnn.pt")); net.eval()
for p in sorted(glob.glob("neuro/real/r*.png")):
    g=cv2.imread(p,0)
    with torch.no_grad(): pred=decode(net(prep(g)).log_softmax(2))[0]
    print(f"{p.split(chr(92))[-1].split('/')[-1]}: {pred}")
