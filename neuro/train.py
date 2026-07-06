import sys, time, random
import numpy as np, cv2, torch, torch.nn as nn
sys.path.insert(0, "neuro")
from synth import sample
from model import CRNN, IMG_H, NCLASS

def prep(g):  # grayscale digits(black)/white -> normalized tensor (1,32,W)
    h,w = g.shape; W = max(16, int(round(w*IMG_H/h))); W=min(W,200)
    g = cv2.resize(g,(W,IMG_H))
    t = torch.from_numpy(255-g).float()/255.0     # ink=1
    return t.unsqueeze(0)

def collate(items):
    imgs=[prep(g) for g,_ in items]; W=max(i.shape[2] for i in imgs)
    x=torch.zeros(len(imgs),1,IMG_H,W)
    for i,im in enumerate(imgs): x[i,:,:,:im.shape[2]]=im
    targets=torch.tensor([int(c) for _,s in items for c in s])
    tlens=torch.tensor([len(s) for _,s in items])
    return x, targets, tlens, W

def batch(bs=48):
    return collate([sample() for _ in range(bs)])

def decode(logp):  # greedy CTC, logp:(T,N,C)
    idx = logp.argmax(2).T.tolist(); out=[]
    for seq in idx:
        s=[]; prev=-1
        for k in seq:
            if k!=10 and k!=prev: s.append(str(k))
            prev=k
        out.append("".join(s))
    return out

def main():
    torch.manual_seed(0); random.seed(0); np.random.seed(0)
    net=CRNN(); opt=torch.optim.Adam(net.parameters(),1e-3)
    ctc=nn.CTCLoss(blank=10, zero_infinity=True)
    steps=int(sys.argv[1]) if len(sys.argv)>1 else 1500
    net.train(); t0=time.time()
    for it in range(1,steps+1):
        x,tg,tl,W=batch()
        logp=net(x).log_softmax(2)
        T=logp.shape[0]; il=torch.full((x.shape[0],),T,dtype=torch.long)
        loss=ctc(logp,tg,il,tl); opt.zero_grad(); loss.backward(); opt.step()
        if it%150==0 or it==steps:
            net.eval()
            with torch.no_grad():
                xv,_,_,_=cb=batch(64); items=[sample() for _ in range(64)]
                xv=collate(items)[0]; pred=decode(net(xv).log_softmax(2))
                gt=[s for _,s in items]; acc=sum(p==g for p,g in zip(pred,gt))/len(gt)
            print(f"step {it:5d} loss {loss.item():.3f} synth_acc {acc:.2f} ({time.time()-t0:.0f}s)")
            net.train()
    torch.save(net.state_dict(), "neuro/crnn.pt")
    print("saved neuro/crnn.pt")

if __name__=="__main__": main()
