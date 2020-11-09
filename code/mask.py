import torch


def _mask_feat(feat, mask, s=1):
    mask_feat = torch.zeros_like(feat)
    d = mask.shape[2]
    r = int(d / 2)
    b, t, h, w = feat.shape

    for i in range(0, h, s):
        for j in range(0, w, s):
            x_min = max(0, i-r)
            x_max = min(h-1, i+r)
            y_min = max(0, j-r)
            y_max = min(w-1, j+r)
            m_x_min = 0 if i-r>=0 else r-i
            m_x_max = d if i+r<h else d-(i+r-h+1)
            m_y_min = 0 if j-r>=0 else r-j
            m_y_max = d if j+r<w else d-(j+r-w+1)
            dx = int(m_x_max-m_x_min)
            dy = int(m_y_max-m_y_min)
            #mask_feat[..., x_min:x_max+1, y_min:y_max+1] += feat[..., i, j].view(b, t, 1, 1) * mask[m_x_min:m_x_max, m_y_min:m_y_max].view(1,1, dx, dy).expand(b,t,dx,dy)
            mask_feat[..., x_min:x_max+1, y_min:y_max+1] += feat[..., i, j].view(b, t, 1, 1) * mask[:, :, m_x_min:m_x_max, m_y_min:m_y_max]
    return mask_feat+feat

def mask_feat(feat, mask, T, s=1):
    for i in range(T):
        feat = _mask_feat(feat, mask, s=s)
    return feat

def logic_and(masks):
    """
    masks: a tensor whose shape is B * T * H * W
    
    Returns:
        compressed mask with operator AND in dim 1
    """
    B, T, H, W = masks.shape
    mask_0 = masks[:, 0]
    for i in range(1, T):
        mask_0 = mask_0 * masks[:, i]
    return mask_0

if __name__ == "__main__":
    masks = torch.ones(4,3,5,5)
    print(logic_and(masks))
