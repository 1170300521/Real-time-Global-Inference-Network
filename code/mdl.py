"""
Model file for zsgnet
Author: Arka Sadhu
"""
import torch
import torch.nn as nn
import numpy as np
# import torch.nn.functional as F
import torchvision.models as tvm
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
from fpn_resnet import FPN_backbone
from anchors import create_grid
import ssd_vgg
from typing import Dict, Any
from extended_config import cfg as conf
from dat_loader import get_data
from afs import AdaptiveFeatureSelection
from garan import GaranAttention
from darknet import darknet53
from controller import Controller
from mask import mask_feat, logic_and

# conv2d, conv2d_relu are adapted from
# https://github.com/fastai/fastai/blob/5c4cefdeaf11fdbbdf876dbe37134c118dca03ad/fastai/layers.py#L98
def conv2d(ni: int, nf: int, ks: int = 3, stride: int = 1,
           padding: int = None, bias=False) -> nn.Conv2d:
    "Create and initialize `nn.Conv2d` layer. `padding` defaults to `ks//2`."
    if padding is None:
        padding = ks//2
    return nn.Conv2d(ni, nf, kernel_size=ks, stride=stride,
                     padding=padding, bias=bias)


def conv2d_relu(ni: int, nf: int, ks: int = 3, stride: int = 1, padding: int = None,
                bn: bool = False, bias: bool = False) -> nn.Sequential:
    """
    Create a `conv2d` layer with `nn.ReLU` activation
    and optional(`bn`) `nn.BatchNorm2d`: `ni` input, `nf` out
    filters, `ks` kernel, `stride`:stride, `padding`:padding,
    `bn`: batch normalization.
    """
    layers = [conv2d(ni, nf, ks=ks, stride=stride,
                     padding=padding, bias=bias), nn.ReLU(inplace=True)]
    if bn:
        layers.append(nn.BatchNorm2d(nf))
    return nn.Sequential(*layers)


class BackBone(nn.Module):
    """
    A general purpose Backbone class.
    For a new network, need to redefine:
    --> encode_feats
    Optionally after_init
    """

    def __init__(self, encoder: nn.Module, cfg: dict, out_chs=256):
        """
        Make required forward hooks
        """
        super().__init__()
        self.device = torch.device(cfg.device)
        self.encoder = encoder
        self.cfg = cfg
        self.out_chs = out_chs
        self.after_init()

    def after_init(self):
        pass

    def num_channels(self):
        raise NotImplementedError

    def concat_we(self, x, we, only_we=False, only_grid=False):
        """
        Convenience function to concat we
        Expects x in the form B x C x H x W (one feature map)
        we: B x wdim (the language vector)
        Output: concatenated word embedding and grid centers
        """
        # Both cannot be true
        assert not (only_we and only_grid)

        # Create the grid
        grid = create_grid((x.size(2), x.size(3)),
                           flatten=False).to(self.device)
        grid = grid.permute(2, 0, 1).contiguous()

        # TODO: Slightly cleaner implementation?
        grid_tile = grid.view(
            1, grid.size(0), grid.size(1), grid.size(2)).expand(
            we.size(0), grid.size(0), grid.size(1), grid.size(2))

        # In case we only need the grid
        # Basically, don't use any image/language information
        if only_grid:
            return grid_tile

        # Expand word embeddings
        word_emb_tile = we.view(
            we.size(0), we.size(1), 1, 1).expand(
                we.size(0), we.size(1), x.size(2), x.size(3))

        # In case performing image blind (requiring only language)
        if only_we:
            return word_emb_tile

        # Concatenate along the channel dimension
        return torch.cat((x, word_emb_tile, grid_tile), dim=1)

    def encode_feats(self, inp):
        return self.encoder(inp)

    def forward(self, inp, we=None,
                only_we=False, only_grid=False, filt_dict=None):
        """
        expecting word embedding of shape B x WE.
        If only image features are needed, don't
        provide any word embedding
        """
        feats,att_maps = self.encode_feats(inp,we, filt_dict=filt_dict)
        # If we want to do normalization of the features
        if self.cfg['do_norm']:
            feats = [
                feat / feat.norm(dim=1).unsqueeze(1).expand(*feat.shape)
                for feat in feats
            ]

        # For language blind setting, can directly return the features
        if we is None:
            return feats

        if self.cfg['do_norm']:
            b, wdim = we.shape
            we = we / we.norm(dim=1).unsqueeze(1).expand(b, wdim)

        out = [self.concat_we(
            f, we, only_we=only_we, only_grid=only_grid) for f in feats]

        return out,att_maps


class RetinaBackBone(BackBone):
    def after_init(self):
        self.num_chs = self.num_channels()
        self.fpn = FPN_backbone([512,512,512], self.cfg, feat_size=self.out_chs).to(self.device)
        self.afs_stage0=AdaptiveFeatureSelection(0,[],2,list(self.num_chs[1:]),self.num_chs[0],256,256,512).to(self.device)
        self.afs_stage1=AdaptiveFeatureSelection(1,[self.num_chs[0]],1,[self.num_chs[-1]],self.num_chs[1],256,256,512).to(self.device)
        self.afs_stage2=AdaptiveFeatureSelection(2,list(self.num_chs[:-1]),0,[],self.num_chs[-1],256,256,512).to(self.device)

        self.garan_stage0 = GaranAttention(256, 512, n_head=2).to(self.device)
        self.garan_stage1 = GaranAttention(256, 512, n_head=2).to(self.device)
        self.garan_stage2 = GaranAttention(256, 512, n_head=2).to(self.device)
    def num_channels(self):
        return [self.encoder.layer2[-1].conv3.out_channels,
                self.encoder.layer3[-1].conv3.out_channels,
                self.encoder.layer4[-1].conv3.out_channels]

    def encode_feats(self, inp,lang, filt_dict=None):
        x = self.encoder.conv1(inp)
        x = self.encoder.bn1(x)
        x = self.encoder.relu(x)
        x = self.encoder.maxpool(x)
        x1 = self.encoder.layer1(x)
        x2 = self.encoder.layer2(x1)
        x3 = self.encoder.layer3(x2)
        x4 = self.encoder.layer4(x3)
        # print(lang.size())
        x2_ = self.afs_stage0(lang,[x2, x3, x4])
        x2_,E_1=self.garan_stage0(lang,x2_)
        x3_ = self.afs_stage1(lang,[x2, x3, x4])
        x3_,E_2 = self.garan_stage1(lang, x3_)
        x4_ = self.afs_stage2(lang,[x2, x3, x4])
        x4_,E_3 = self.garan_stage2(lang, x4_)
        feats = self.fpn([x2_, x3_, x4_])
        return feats,[E_1,E_2,E_3]


class SSDBackBone(BackBone):
    """
    ssd_vgg.py already implements encoder
    """

    def encode_feats(self, inp):
        return self.encoder(inp)


class YoloBackBone(BackBone):
    def after_init(self):
        self.num_chs = self.num_channels()
        self.n_head = 4
        self.afs_stage=AdaptiveFeatureSelection(2, [256, 512], 0, [], self.num_chs[-1], 2048,512,1024).to(self.device)

        self.garan_stage = GaranAttention(2048, 1024, n_head=self.n_head).to(self.device)
    def num_channels(self):
        return [256, 512, 1024]
    def encode_feats(self, inp,lang, filt_dict=None):
        x2, x3, x4 = self.encoder(inp)
        # print(lang.size())
        filter1 = filt_dict['f1']
        filter2 = filt_dict['f2']
        filter3 = filt_dict['f3']
        rel_filter = filt_dict['rel']
        B, T, _, _ = rel_filter.shape
        x_, visual_feat = self.afs_stage(lang,[x2, x3, x4])

        dup_feat = [f.squeeze().unsqueeze(1).expand(-1, T, -1, -1, -1) for f in visual_feat] # B*T*C*H*W
        heat_map = (filter1*dup_feat[0] + filter2*dup_feat[1] + filter3*dup_feat[2]).sum(dim=2)  # B * T * H * W
        masks = mask_feat(heat_map, rel_filter)  # B * T * H * W
        mask = logic_and(masks).contiguous() # B * H * W
        B, H, W = mask.shape
        mask = mask.view(B, 1, H*W).expand(B, self.n_head, -1).contiguous().view(B*self.n_head, 1, H*W) 

        feats, E=self.garan_stage(lang,x_, mask=mask)

        # Special case, the number of feature map is one.
        return [feats], [E]


class ZSGNet(nn.Module):
    """
    The main model
    Uses SSD like architecture but for Lang+Vision
    """

    def __init__(self, backbone, n_anchors=1, final_bias=0., cfg=None):
        super().__init__()
        # assert isinstance(backbone, BackBone)
        self.backbone = backbone

        # Assume the output from each
        # component of backbone will have 256 channels
        self.device = torch.device(cfg.device)

        self.cfg = cfg

        # should be len(ratios) * len(scales)
        self.n_anchors = n_anchors

        self.is_lstm = cfg['lang_to_use'] == 'lstm'
        self.emb_dim = cfg['emb_dim']
        self.bid = cfg['use_bidirectional']
        self.lstm_dim = cfg['lstm_dim']
        self.img_dim = cfg['img_dim']

        # Calculate output dimension of LSTM
        self.lstm_out_dim = self.lstm_dim * (self.bid + 1)

        # Separate cases for language, image blind settings
        if self.cfg['use_lang'] and self.cfg['use_img']:
            self.start_dim_head = self.lstm_dim*(self.bid+1) + self.img_dim + 2
        elif self.cfg['use_img'] and not self.cfg['use_lang']:
            # language blind
            self.start_dim_head = self.img_dim
        elif self.cfg['use_lang'] and not self.cfg['use_img']:
            # image blind
            self.start_dim_head = self.lstm_dim*(self.bid+1)
        else:
            # both image, lang blind
            self.start_dim_head = 2

        # If shared heads for classification, box regression
        # This is the config used in the paper
        if self.cfg['use_same_atb']:
            bias = torch.zeros(5 * self.n_anchors)
            bias[torch.arange(4, 5 * self.n_anchors, 5)] = -4
            self.att_reg_box = self._head_subnet(
                5, self.n_anchors, final_bias=bias,
                start_dim_head=self.start_dim_head
            )
        # This is not used. Kept for historical purposes
        else:
            self.att_box = self._head_subnet(
                1, self.n_anchors, -4., start_dim_head=self.start_dim_head)
            self.reg_box = self._head_subnet(
                4, self.n_anchors, start_dim_head=self.start_dim_head)

        if self.is_lstm:
            self.lstm = nn.LSTM(self.emb_dim, self.lstm_dim,
                                bidirectional=self.bid, batch_first=False)
        else:
            self.gru = nn.GRU(self.emb_dim, self.lstm_dim, 
                                bidirectional=self.bid, batch_first=False)
        
        if self.cfg.relation:
            lstm_out_dim = self.lstm_dim * (self.bid + 1)
            self.soft_parser = Controller(lstm_out_dim, self.cfg.T_obj) 
            # object filter
            self.k1 = nn.Linear(lstm_out_dim, self.img_dim)
            self.k2 = nn.Linear(lstm_out_dim, self.img_dim)
            self.k3 = nn.Linear(lstm_out_dim, self.img_dim)
    
            # relation kernel
            self.kernel = nn.Sequential(
                    nn.Linear(lstm_out_dim, int(lstm_out_dim/2)),
                    nn.LeakyReLU(0.1, inplace=True),
#                    nn.BatchNorm2d(int(lstm_out_dim/2)),
                    nn.Linear(int(lstm_out_dim/2), 9),
                    nn.LeakyReLU(0.1, inplace=True),
#                    nn.BatchNorm2d(9),
                    nn.Softmax(dim=1)
                )
        self.after_init()

    def after_init(self):
        "Placeholder if any child class needs something more"
        pass

    def _head_subnet(self, n_classes, n_anchors, final_bias=0., n_conv=4, chs=256,
                     start_dim_head=256):
        """
        Convenience function to create attention and regression heads
        """
        layers = [conv2d_relu(start_dim_head, chs, bias=True)]
        layers += [conv2d_relu(chs, chs, bias=True) for _ in range(n_conv)]
        layers += [conv2d(chs, n_classes * n_anchors, bias=True)]
        layers[-1].bias.data.zero_().add_(final_bias)
        return nn.Sequential(*layers)

    def permute_correctly(self, inp, outc):
        """
        Basically square box features are flattened
        """
        # inp is features
        # B x C x H x W -> B x H x W x C
        out = inp.permute(0, 2, 3, 1).contiguous()
        out = out.view(out.size(0), -1, outc)
        return out

    def concat_we(self, x, we, append_grid_centers=True):
        """
        Convenience function to concat we
        Expects x in the form B x C x H x W
        we: B x wdim
        """
        b, wdim = we.shape
        we = we / we.norm(dim=1).unsqueeze(1).expand(b, wdim)
        word_emb_tile = we.view(we.size(0), we.size(1),
                                1, 1).expand(we.size(0),
                                             we.size(1),
                                             x.size(2), x.size(3))

        if append_grid_centers:
            grid = create_grid((x.size(2), x.size(3)),
                               flatten=False).to(self.device)
            grid = grid.permute(2, 0, 1).contiguous()
            grid_tile = grid.view(1, grid.size(0), grid.size(1), grid.size(2)).expand(
                we.size(0), grid.size(0), grid.size(1), grid.size(2))

            return torch.cat((x, word_emb_tile, grid_tile), dim=1)
        return torch.cat((x, word_emb_tile), dim=1)

    def lstm_init_hidden(self, bs):
        """
        Initialize the very first hidden state of LSTM
        Basically, the LSTM should be independent of this
        """
        if not self.bid:
            hidden_a = torch.randn(1, bs, self.lstm_dim)
            hidden_b = torch.randn(1, bs, self.lstm_dim)
        else:
            hidden_a = torch.randn(2, bs, self.lstm_dim)
            hidden_b = torch.randn(2, bs, self.lstm_dim)

        hidden_a = hidden_a.to(self.device)
        hidden_b = hidden_b.to(self.device)
        if self.is_lstm:
            return (hidden_a, hidden_b)
        else:
            return hidden_a

    def apply_lstm(self, word_embs, qlens, max_qlen, get_full_seq=False):
        """
        Applies lstm function.
        word_embs: word embeddings, B x seq_len x 300
        qlen: length of the phrases
        Try not to fiddle with this function.
        IT JUST WORKS
        """
        # B x T x E
        bs, max_seq_len, emb_dim = word_embs.shape
        # bid x B x L
        self.hidden = self.lstm_init_hidden(bs)
        # B x 1, B x 1
        qlens1, perm_idx = qlens.sort(0, descending=True)
        # B x T x E (permuted)
        qtoks = word_embs[perm_idx]
        # T x B x E
        embeds = qtoks.permute(1, 0, 2).contiguous()
        # Packed Embeddings
        packed_embed_inp = pack_padded_sequence(
            embeds, lengths=qlens1, batch_first=False)
        # To ensure no pains with DataParallel
        # self.lstm.flatten_parameters()
        if self.is_lstm:
            lstm_out1, (self.hidden, _) = self.lstm(packed_embed_inp, self.hidden)
        else:
            lstm_out1, self.hidden = self.gru(packed_embed_inp, self.hidden)

        # T x B x L
        lstm_out, req_lens = pad_packed_sequence(
            lstm_out1, batch_first=False, total_length=max_qlen)

        # TODO: Simplify getting the last vector
        masks = (qlens1-1).view(1, -1, 1).expand(max_qlen,
                                                 lstm_out.size(1), lstm_out.size(2))
        qvec_sorted = lstm_out.gather(0, masks.long())[0]

        qvec_out = word_embs.new_zeros(qvec_sorted.shape)
        qvec_out[perm_idx] = qvec_sorted
        qvec_out = qvec_out.contiguous()
        # if full sequence is needed for future work
        if get_full_seq:
            # get words mask
            ids = torch.arange(max_qlen).unsqueeze(0).expand(bs, max_qlen).float().to(qvec_out.device)
            att_mask = (ids < qlens.view(-1, 1)).float()
            lstm_out_1 = lstm_out.transpose(1, 0)
            lstm_out = lstm_out_1[perm_idx].contiguous()
            return lstm_out, qvec_out, att_mask
        return qvec_out

    def forward(self, inp: Dict[str, Any]):
        """
        Forward method of the model
        inp0 : image to be used
        inp1 : word embeddings, B x seq_len x 300
        qlens: length of phrases

        The following is performed:
        1. Get final hidden state features of lstm
        2. Get image feature maps
        3. Concatenate the two, specifically, copy lang features
        and append it to all the image feature maps, also append the
        grid centers.
        4. Use the classification, regression head on this concatenated features
        The matching with groundtruth is done in loss function and evaluation
        """
        inp0 = inp['img']
        inp1 = inp['qvec']
        qlens = inp['qlens']
        max_qlen = int(qlens.max().item())
        req_embs = inp1[:, :max_qlen, :].contiguous()

        lstm_out, req_emb, att_mask = self.apply_lstm(req_embs, qlens, max_qlen, get_full_seq=self.cfg.relation)
        
        # get parser results
        if self.cfg.relation:
            _, sub_exp = self.soft_parser(lstm_out, req_emb, att_mask)
            B, T, _ = sub_exp.shape
            filter1 = self.k1(sub_exp).view(B, T, -1, 1, 1)
            filter2 = self.k2(sub_exp).view(B, T, -1, 1, 1)
            filter3 = self.k3(sub_exp).view(B, T, -1, 1, 1) # B * T * C
            rel_filter = self.kernel(sub_exp) # B * T * k^2
            B, T, k2 = rel_filter.shape
            k = int(np.sqrt(k2))
            rel_filter = rel_filter.view(B, T, k, k)
            filt_dict = {
                    "f1": filter1,
                    "f2": filter2,
                    "f3": filter3,
                    "rel": rel_filter
                    }

        # image blind
        if self.cfg['use_lang'] and not self.cfg['use_img']:
            # feat_out = self.backbone(inp0)
            feat_out,E_attns = self.backbone(inp0, req_emb, only_we=True)

        # language blind
        elif self.cfg['use_img'] and not self.cfg['use_lang']:
            feat_out,E_attns = self.backbone(inp0)

        elif not self.cfg['use_img'] and not self.cfg['use_lang']:
            feat_out,E_attns = self.backbone(inp0, req_emb, only_grid=True)
        # see full language + image (happens by default)
        else:
            feat_out,E_attns = self.backbone(inp0, req_emb, filt_dict=filt_dict)


        # Strategy depending on shared head or not
        if self.cfg['use_same_atb']:
            att_bbx_out = torch.cat([self.permute_correctly(
                self.att_reg_box(feature), 5) for feature in feat_out], dim=1)
            att_out = att_bbx_out[..., [-1]]
            bbx_out = att_bbx_out[..., :-1]
        else:
            att_out = torch.cat(
                [self.permute_correctly(self.att_box(feature), 1)
                 for feature in feat_out], dim=1)
            bbx_out = torch.cat(
                [self.permute_correctly(self.reg_box(feature), 4)
                 for feature in feat_out], dim=1)

        feat_sizes = torch.tensor([[f.size(2), f.size(3)]
                                   for f in feat_out]).to(self.device)

        # Used mainly due to dataparallel consistency
        num_f_out = torch.tensor([len(feat_out)]).to(self.device)

        out_dict = {}
        out_dict['att_out'] = att_out
        out_dict['bbx_out'] = bbx_out
        out_dict['feat_sizes'] = feat_sizes
        out_dict['num_f_out'] = num_f_out
        out_dict['att_maps'] = E_attns
        return out_dict


def get_default_net(num_anchors=1, cfg=None):
    """
    Constructs the network based on the config
    """
    if cfg['mdl_to_use'] == 'retina':
        encoder = tvm.resnet50(True)
        backbone = RetinaBackBone(encoder, cfg)
    elif cfg['mdl_to_use'] == 'ssd_vgg':
        encoder = ssd_vgg.build_ssd('train', cfg=cfg)
        encoder.vgg.load_state_dict(
            torch.load('./weights/vgg16_reducedfc.pth'))
        print('loaded pretrained vgg backbone')
        backbone = SSDBackBone(encoder, cfg)
        # backbone = encoder
    elif cfg['mdl_to_use'] == 'realgin':
        encoder = darknet53(True)
        backbone = YoloBackBone(encoder, cfg)

    zsg_net = ZSGNet(backbone, num_anchors, cfg=cfg)
    return zsg_net


if __name__ == '__main__':
    # torch.manual_seed(0)
    cfg = conf
    cfg.mdl_to_use = 'ssd_vgg'
    cfg.ds_to_use = 'refclef'
    cfg.num_gpus = 1
    # cfg.device = 'cpu'
    device = torch.device(cfg.device)
    data = get_data(cfg)

    zsg_net = get_default_net(num_anchors=9, cfg=cfg)
    zsg_net.to(device)

    batch = next(iter(data.train_dl))
    for k in batch:
        batch[k] = batch[k].to(device)
    out = zsg_net(batch)
