"""纯 Python ed25519（RFC 8032）签名与验签，零依赖，仅用标准库。

self_update.py --apply 用其中的 verify() 校验 manifest.json 签名；
tools/sign_manifest.py 用 sign() 生成签名。验签性能不在关键路径上
（每次更新只验一次），实现取教科书式的扩展坐标点运算，求正确不求快。

密钥编码：私钥 = 32 字节种子（hex/base64 存储）；公钥 = 32 字节 RFC 8032
标准压缩编码；签名 = 64 字节 R‖S。
"""
import hashlib

# 域参数：GF(2^255 - 19)，曲线 -x² + y² = 1 + d·x²·y²
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493  # 群的阶
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)  # sqrt(-1)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = x * _I % _P
    if x & 1:
        x = _P - x
    return x


_BY = (4 * pow(5, _P - 2, _P)) % _P
_BX = _xrecover(_BY)
# 基点（扩展坐标 x, y, z, t，x=X/Z, y=Y/Z, t=XY/Z）
_B = (_BX, _BY, 1, _BX * _BY % _P)
_IDENTITY = (0, 1, 1, 0)


def _point_add(P, Q):
    x1, y1, z1, t1 = P
    x2, y2, z2, t2 = Q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * _D * t1 * t2 % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalarmult(P, e: int):
    Q = _IDENTITY
    while e > 0:
        if e & 1:
            Q = _point_add(Q, P)
        P = _point_add(P, P)
        e >>= 1
    return Q


def _encode_point(P) -> bytes:
    x, y, z, _t = P
    zi = pow(z, _P - 2, _P)
    x, y = x * zi % _P, y * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decode_point(s: bytes):
    if len(s) != 32:
        raise ValueError("点编码长度须为 32 字节")
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    if y >= _P:
        raise ValueError("点编码 y 坐标越界")
    x = _xrecover(y)
    if (x & 1) != (s[31] >> 7):
        x = _P - x
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P != 0:
        raise ValueError("点不在曲线上")
    return (x, y, 1, x * y % _P)


def _hint(m: bytes) -> int:
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _secret_expand(seed: bytes):
    if len(seed) != 32:
        raise ValueError("私钥种子须为 32 字节")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def publickey(seed: bytes) -> bytes:
    """32 字节种子 → 32 字节公钥。"""
    a, _prefix = _secret_expand(seed)
    return _encode_point(_scalarmult(_B, a))


def sign(seed: bytes, msg: bytes) -> bytes:
    """RFC 8032 确定性签名：64 字节 R‖S。仅发版工具（tools/）使用。"""
    a, prefix = _secret_expand(seed)
    A = publickey(seed)
    r = _hint(prefix + msg) % _Q
    R = _encode_point(_scalarmult(_B, r))
    S = (r + _hint(R + A + msg) * a) % _Q
    return R + S.to_bytes(32, "little")


def verify(pk: bytes, msg: bytes, sig: bytes) -> bool:
    """验签：通过返回 True；任何不符（含畸形输入）返回 False，不抛异常。"""
    if len(pk) != 32 or len(sig) != 64:
        return False
    R, s = sig[:32], int.from_bytes(sig[32:], "little")
    if s >= _Q:
        return False
    try:
        A = _decode_point(pk)
        Rpt = _decode_point(R)
    except ValueError:
        return False
    h = _hint(R + pk + msg) % _Q
    # [S]B == R + [h]A
    return _encode_point(_scalarmult(_B, s)) == _encode_point(
        _point_add(Rpt, _scalarmult(A, h)))


def fingerprint(pk: bytes) -> str:
    """公钥指纹：SHA256(公钥) 十六进制，用于注释与审计对照。"""
    return hashlib.sha256(pk).hexdigest()
