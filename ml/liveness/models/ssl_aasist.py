"""AASIST with a self-supervised front end (wav2vec 2.0 XLS-R), after Tak et
al., "Automatic speaker verification spoofing and deepfake detection using
wav2vec 2.0 and data augmentation" (Odyssey 2022).

AASIST's own front end is a bank of sinc filters learned from the anti-spoofing
data alone. Here it's replaced by XLS-R, which learned what speech sounds like
from about 436,000 hours of real recordings in 128 languages, across many
microphones and rooms. Its features are projected to 128 numbers per frame and
fed to the same AASIST graph back end (models/aasist.py, unchanged). Both parts
are trained together; the back end starts from scratch.

Input and output are the same as models.aasist.Model: (batch, samples) at
16 kHz in, (last_hidden, logits) out, logits[:, 1] the "real" score.
"""

import torch
import torch.nn.functional as F
from torch import nn
from transformers import Wav2Vec2Config, Wav2Vec2Model

from models.aasist import Model as Aasist

SSL_NAME = "facebook/wav2vec2-xls-r-300m"
FEATURES = 128  # per frame, after the projection; AASIST's "frequency" axis


class SslAasist(Aasist):
    def __init__(self, d_args: dict, ssl: str | Wav2Vec2Config = SSL_NAME):
        super().__init__(d_args)
        # The sinc front end isn't used.
        del self.conv_time
        # A name downloads the pretrained model; a config builds an untrained
        # one of that shape (tests, and loading our own fine-tuned weights).
        self.ssl = Wav2Vec2Model(ssl) if isinstance(ssl, Wav2Vec2Config) else Wav2Vec2Model.from_pretrained(ssl)
        # The convolutional feature encoder stays as pretrained: fine-tuning it
        # on a few datasets mostly overfits.
        self.ssl.freeze_feature_encoder()
        self.project = nn.Linear(self.ssl.config.hidden_size, FEATURES)
        # One position embedding per "frequency" row reaching the graph:
        # 128 features, max-pooled by 3, leave 42 (the sinc front end's 70 left 23).
        filts = d_args["filts"]
        self.pos_S = nn.Parameter(torch.randn(1, FEATURES // 3, filts[-1][-1]))
        # XLS-R gives 50 frames a second, about 67 after the first pooling for
        # 4 seconds; each encoder block's own time pooling (by 3) would leave
        # none after four blocks. The sinc front end had thousands of samples
        # to pool; here every frame is kept.
        for block in self.encoder:
            block[0].mp = nn.Identity()

    def ssl_parameters(self):
        return self.ssl.parameters()

    def backend_parameters(self):
        ssl = {id(p) for p in self.ssl.parameters()}
        return [p for p in self.parameters() if id(p) not in ssl]

    def forward(self, x, Freq_aug=False):  # same signature as Aasist; Freq_aug is unused
        # XLS-R expects each clip at zero mean and unit variance.
        x = (x - x.mean(dim=1, keepdim=True)) / torch.sqrt(x.var(dim=1, keepdim=True) + 1e-7)
        frames = self.ssl(x).last_hidden_state  # (batch, frames, 1024): 50 frames a second
        x = self.project(frames).transpose(1, 2).unsqueeze(1)  # (batch, 1, 128, frames)
        x = F.max_pool2d(x, (3, 3))
        x = self.first_bn(x)
        x = self.selu(x)
        return self._back_end(x)

    def _back_end(self, x):
        # From here on, exactly Aasist.forward after its front end.
        e = self.encoder(x)

        e_S, _ = torch.max(torch.abs(e), dim=3)
        e_S = e_S.transpose(1, 2) + self.pos_S
        gat_S = self.GAT_layer_S(e_S)
        out_S = self.pool_S(gat_S)

        e_T, _ = torch.max(torch.abs(e), dim=2)
        e_T = e_T.transpose(1, 2)
        gat_T = self.GAT_layer_T(e_T)
        out_T = self.pool_T(gat_T)

        master1 = self.master1.expand(x.size(0), -1, -1)
        master2 = self.master2.expand(x.size(0), -1, -1)

        out_T1, out_S1, master1 = self.HtrgGAT_layer_ST11(out_T, out_S, master=self.master1)
        out_S1 = self.pool_hS1(out_S1)
        out_T1 = self.pool_hT1(out_T1)
        out_T_aug, out_S_aug, master_aug = self.HtrgGAT_layer_ST12(out_T1, out_S1, master=master1)
        out_T1 = out_T1 + out_T_aug
        out_S1 = out_S1 + out_S_aug
        master1 = master1 + master_aug

        out_T2, out_S2, master2 = self.HtrgGAT_layer_ST21(out_T, out_S, master=self.master2)
        out_S2 = self.pool_hS2(out_S2)
        out_T2 = self.pool_hT2(out_T2)
        out_T_aug, out_S_aug, master_aug = self.HtrgGAT_layer_ST22(out_T2, out_S2, master=master2)
        out_T2 = out_T2 + out_T_aug
        out_S2 = out_S2 + out_S_aug
        master2 = master2 + master_aug

        out_T1 = self.drop_way(out_T1)
        out_T2 = self.drop_way(out_T2)
        out_S1 = self.drop_way(out_S1)
        out_S2 = self.drop_way(out_S2)
        master1 = self.drop_way(master1)
        master2 = self.drop_way(master2)

        out_T = torch.max(out_T1, out_T2)
        out_S = torch.max(out_S1, out_S2)
        master = torch.max(master1, master2)

        T_max, _ = torch.max(torch.abs(out_T), dim=1)
        T_avg = torch.mean(out_T, dim=1)
        S_max, _ = torch.max(torch.abs(out_S), dim=1)
        S_avg = torch.mean(out_S, dim=1)

        last_hidden = torch.cat([T_max, T_avg, S_max, S_avg, master.squeeze(1)], dim=1)
        last_hidden = self.drop(last_hidden)
        return last_hidden, self.out_layer(last_hidden)


def is_ssl_checkpoint(state: dict) -> bool:
    return any(key.startswith("ssl.") for key in state)
