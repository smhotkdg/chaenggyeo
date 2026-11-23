"""글자 단위 소형 모델: 트리거 분류 + 슬롯(물건·장소·들를 곳) 추출 공동 학습.

사전학습 모델 없이 처음부터 학습한다 (실험 환경에서 HuggingFace 접근 불가).
사용법: python3 train.py [train.jsonl] [--arch gru|tf]
"""
import json
import os
import sys
import time

import torch
import torch.nn as nn

from test_set import TEST

torch.manual_seed(0)
torch.set_num_threads(2)

# ---------- 어휘: 한글 완성형 전체 + 자모 + ASCII (처음 보는 물건 이름도 UNK 없이 처리)
CHARS = [chr(c) for c in range(0xAC00, 0xD7A4)] + [chr(c) for c in range(0x3131, 0x3164)] + \
        [chr(c) for c in range(32, 127)] + list("…·~“”‘’")
VOCAB = {c: i + 2 for i, c in enumerate(CHARS)}  # 0=PAD, 1=UNK
TAGS = ["O", "B-ITEM", "I-ITEM", "B-PLACE", "I-PLACE", "B-STOP", "I-STOP"]
HEADS = {
    "trigger": ["arrive", "depart", "en_route"],
    "anchor": ["home", "work", "other"],
    "origin": ["none", "current", "home", "work"],
    "action": ["pick_up", "buy", "drop_off"],
}
MAXLEN = 48


def encode(text):
    ids = [VOCAB.get(c, 1) for c in text[:MAXLEN]]
    return ids


class Model(nn.Module):
    def __init__(self, arch="gru", emb=96, hid=128):
        super().__init__()
        self.arch = arch
        self.emb = nn.Embedding(len(VOCAB) + 2, emb, padding_idx=0)
        if arch == "gru":
            self.enc = nn.GRU(emb, hid, num_layers=2, batch_first=True, bidirectional=True, dropout=0.1)
            d = hid * 2
        else:
            self.pos = nn.Embedding(MAXLEN, emb)
            layer = nn.TransformerEncoderLayer(emb, 4, emb * 2, dropout=0.1, batch_first=True)
            self.enc = nn.TransformerEncoder(layer, 3)
            d = emb
        self.tag = nn.Linear(d, len(TAGS))
        self.heads = nn.ModuleDict({k: nn.Linear(d * 2, len(v)) for k, v in HEADS.items()})

    def forward(self, x):
        mask = (x != 0).unsqueeze(-1).float()
        h = self.emb(x)
        if self.arch == "gru":
            h, _ = self.enc(h)
        else:
            h = h + self.pos(torch.arange(x.size(1)).unsqueeze(0))
            h = self.enc(h, src_key_padding_mask=(x == 0))
        mean = (h * mask).sum(1) / mask.sum(1).clamp(min=1)
        mx = (h + (mask - 1) * 1e4).max(1).values
        pooled = torch.cat([mean, mx], -1)
        return self.tag(h), {k: m(pooled) for k, m in self.heads.items()}


def batchify(recs):
    L = max(len(r["text"][:MAXLEN]) for r in recs)
    x = torch.zeros(len(recs), L, dtype=torch.long)
    y = torch.full((len(recs), L), -100, dtype=torch.long)
    hy = {k: torch.tensor([HEADS[k].index(r[k]) for r in recs]) for k in HEADS}
    for i, r in enumerate(recs):
        ids = encode(r["text"])
        x[i, :len(ids)] = torch.tensor(ids)
        if "tags" in r and isinstance(r["tags"], list):
            y[i, :len(ids)] = torch.tensor([TAGS.index(t) for t in r["tags"][:MAXLEN]])
    return x, y, hy


def spans(text, tag_ids):
    out = {}
    cur, start = None, 0
    seq = [TAGS[t] for t in tag_ids] + ["O"]
    for i, t in enumerate(seq):
        typ = t[2:] if t != "O" else None
        if cur and (t == "O" or t.startswith("B-") or typ != cur):
            out.setdefault(cur, text[start:i].strip())
            cur = None
        if t.startswith("B-") or (t.startswith("I-") and cur is None):
            cur, start = typ, i
    return out


@torch.no_grad()
def predict(model, texts):
    model.eval()
    recs = [{"text": t, **{k: v[0] for k, v in HEADS.items()}} for t in texts]
    x, _, _ = batchify(recs)
    tl, hl = model(x)
    res = []
    for i, t in enumerate(texts):
        n = len(encode(t))
        sp = spans(t, tl[i, :n].argmax(-1).tolist())
        r = {k: HEADS[k][hl[k][i].argmax().item()] for k in HEADS}
        r.update(item=sp.get("ITEM"), place=sp.get("PLACE"), stop=sp.get("STOP"))
        res.append(r)
    return res


def norm(s):
    return s.replace(" ", "") if s else s


def evaluate(model, data, label=""):
    preds = predict(model, [d["text"] for d in data])
    keys = ["trigger", "anchor", "origin", "item", "place", "stop"]
    acc = {k: 0 for k in keys + ["action", "frame"]}
    errs = []
    for d, p in zip(data, preds):
        ok_all = True
        for k in keys:
            ok = norm(d[k]) == norm(p[k]) if k in ("item", "place", "stop") else d[k] == p[k]
            acc[k] += ok
            ok_all &= ok
        acc["action"] += d["action"] == p["action"]
        acc["frame"] += ok_all
        if not ok_all:
            errs.append((d, p))
    n = len(data)
    return {k: round(v / n * 100, 1) for k, v in acc.items()}, errs


def main():
    path = next((a for a in sys.argv[1:] if a.endswith(".jsonl")), "train.jsonl")
    arch = "tf" if "--arch=tf" in sys.argv else "gru"
    data = [json.loads(l) for l in open(path, encoding="utf-8")]
    dev, train = data[:3000], data[3000:]
    model = Model(arch)
    nparam = sum(p.numel() for p in model.parameters())
    print(f"arch={arch} params={nparam:,} train={len(train)}")
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    ce = nn.CrossEntropyLoss(ignore_index=-100)
    B, EPOCHS = 128, int(os.environ.get("EPOCHS", 6))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 2e-3, total_steps=EPOCHS * (len(train) // B + 1))
    g = torch.Generator().manual_seed(0)
    for ep in range(EPOCHS):
        model.train()
        t0, tot = time.time(), 0
        perm = torch.randperm(len(train), generator=g).tolist()
        for s in range(0, len(train), B):
            x, y, hy = batchify([train[i] for i in perm[s:s + B]])
            tl, hl = model(x)
            loss = ce(tl.reshape(-1, len(TAGS)), y.reshape(-1)) + sum(ce(hl[k], hy[k]) for k in HEADS)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            tot += loss.item()
        dv, _ = evaluate(model, dev)
        ts, _ = evaluate(model, TEST)
        print(f"ep{ep} loss={tot / (len(train) / B):.3f} {time.time() - t0:.0f}s dev_frame={dv['frame']} test={ts}")
    torch.save(model.state_dict(), f"model_{arch}.pt")
    return model


if __name__ == "__main__":
    main()
