"""Малый CRNN + CTC: читает номер (последовательность цифр) с кропа без
посимвольной сегментации. Экспортируется в ONNX для офлайн-инференса."""
import torch, torch.nn as nn

IMG_H = 32
NCLASS = 11  # 0-9 + blank(10)

class CRNN(nn.Module):
    def __init__(self, nclass=NCLASS):
        super().__init__()
        def blk(i,o,p=True):
            layers=[nn.Conv2d(i,o,3,1,1), nn.BatchNorm2d(o), nn.ReLU(inplace=True)]
            if p: layers.append(nn.MaxPool2d(2,2))
            return layers
        self.cnn = nn.Sequential(
            *blk(1,32), *blk(32,64), *blk(64,128,p=False),
            nn.MaxPool2d((2,1),(2,1)),
            *blk(128,128,p=False), nn.MaxPool2d((2,1),(2,1)),
        )  # H:32->16->8->4->2->1
        self.rnn = nn.LSTM(128, 96, num_layers=2, bidirectional=True, batch_first=False)
        self.fc = nn.Linear(192, nclass)
    def forward(self, x):           # x: (N,1,32,W)
        f = self.cnn(x)             # (N,128,h,W')
        f = torch.nn.functional.adaptive_avg_pool2d(f, (1, f.shape[3]))
        f = f.squeeze(2).permute(2,0,1)   # (W',N,128)
        r,_ = self.rnn(f)
        return self.fc(r)           # (W',N,nclass)  -> CTC logits
