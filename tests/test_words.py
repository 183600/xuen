"""词库清洗测试：LLM 输出的 markdown 装饰/编号不能以残片形式混进词库。

清洗结果会写进 words.txt，并由 load_words 再次清洗读取；残片随词库
进入每轮提示词。这里锁住三类回归：
  - 成对装饰符后跟解释时收尾符必须连配对一起剥掉；
  - 分隔符列出的多项词表每一段都要剥装饰/序号；
  - 下划线不能在词中配对（"_private_var" 是术语，不是斜体）。
"""
from xuen.words import _clean_line, parse_word_lines


def test_words_clean_unwraps_decorated_terms_with_annotation():
    """词头成对装饰符后跟解释时不能留下残片。

    回归：LLM 常输出 "- **术语**（解释）"、"*术语*: 说明" 这类 markdown；
    收尾装饰符被后面的解释挡在串尾之外，只按两端字符剥离会留下
    "术语**（解释）"、"术语*" 残片混进词库，再被当作灵感词拼进每轮
    提示词。成对装饰符（**、*、`、引号等）必须连收尾一起剥掉，
    同时不能误伤词中装饰（"C*代数"）或纯数字/表达式（"2**10"）。
    """
    assert _clean_line("- **Term** (explanation)") == "Term (explanation)"
    assert _clean_line("*术语*（解释）") == "术语（解释）"
    assert _clean_line("- `梯度下降`（Gradient Descent）") \
        == "梯度下降（Gradient Descent）"
    assert _clean_line("“生成模型”（generative model）") \
        == "生成模型（generative model）"
    assert _clean_line("「**术语**（x）」") == "术语（x）"
    assert _clean_line("- **C**语言") == "C语言"
    assert _clean_line("**Term**") == "Term"
    assert _clean_line("__init__") == "init"
    # 不能误伤：装饰符在词中 / 没有配对的收尾符
    assert _clean_line("2**10") == "2**10"
    assert _clean_line("C*代数") == "C*代数"
    assert _clean_line("*args") == "args"
    assert _clean_line("**kwargs") == "kwargs"
    assert _clean_line("- Term (explanation)") == "Term (explanation)"
    # 清洗必须是不动点：保存到 words.txt 的词 load_words 再洗一遍不能变
    for src in ("- **Term** (explanation)", "*术语*（解释）", "「**术语**（x）」"):
        w = _clean_line(src)
        assert _clean_line(w) == w, w
    assert parse_word_lines("- **注意力机制**（Attention）\n2**10\n") \
        == ["注意力机制（Attention）", "2**10"]


def test_words_clean_keeps_intraword_underscores_and_leading_edge_chars():
    """下划线不能在词中配对；装饰头与边缘字符相邻时也要剥干净。

    回归 1：下划线被当作强调符后，"_private_var" 的词中下划线被当成收尾
    符吃掉、词形变成 "privatevar"（"_loss_fn" → "lossfn"），而 CommonMark
    明确规定 "_" 不能在词中配对，这类下划线是术语本身的一部分。
    回归 2："。**词**（解释）" 这类装饰头与其它边缘字符直接相邻的写法，
    一次性 strip 边缘字符会把 "." 和装饰头一起吃掉，收尾符失去配对接
    留在串中（"词**（解释）"），必须逐个剥离、露头即 unwrap。
    """
    # 词中下划线必须保留（旧版只剥两端时即如此，不能被装饰符逻辑吃回）
    assert _clean_line("_private_var") == "private_var"
    assert _clean_line("_loss_fn（说明）") == "loss_fn（说明）"
    assert _clean_line("_grad_accum: 梯度累积") == "grad_accum"
    assert _clean_line("_x_1") == "x_1"
    # 整体斜体下划线对仍要连收尾一起剥
    assert _clean_line("__init__") == "init"
    assert _clean_line("_术语_（解释）") == "术语（解释）"
    assert _clean_line("___粗斜___（说明）") == "粗斜（说明）"
    # 装饰头与边缘字符相邻：收尾符不能留在词中
    assert _clean_line(".**词**（解释）") == "词（解释）"
    assert _clean_line("、**词**（说明）") == "词（说明）"
    assert _clean_line(".「术语」（解释）") == "术语（解释）"
    # 清洗必须是不动点：保存到 words.txt 的词 load_words 再洗一遍不能变
    for src in ("_private_var", "__init__", ".**词**（解释）", "_术语_（解释）"):
        w = _clean_line(src)
        assert w is not None
        assert _clean_line(w) == w, w


def test_words_clean_unwraps_each_segment_after_separators():
    """同一行分隔符列出的多个装饰术语必须逐段剥干净。

    回归：LLM 常输出 "**卷积**、**池化**、**全连接**"、"*fast*, *slow*"。
    只从整行词头 unwrap 时仅第一段被剥，后续段的收尾被 rstrip(_EDGE_CHARS)
    剥掉、装饰头却留在词中（"卷积、**池化、**全连接"），残片随词库进入
    每轮提示词。按分隔符分段后每段都要能剥掉自己的装饰头/收尾。
    """
    assert _clean_line("**卷积**、**池化**、**全连接**") == "卷积、池化、全连接"
    assert _clean_line("1. **卷积**、**池化**、**全连接**") == "卷积、池化、全连接"
    assert _clean_line("*fast*, *slow*") == "fast, slow"
    assert _clean_line("`a`, `b`") == "a, b"
    assert _clean_line("*α*、*β*、*γ*") == "α、β、γ"
    assert _clean_line("*a*; *b*; *c*") == "a; b; c"
    assert _clean_line('"a", "b"') == "a, b"
    assert _clean_line("「a」、「b」") == "a、b"
    # 单个装饰对跨分隔符时整体剥掉，不被分段撕开
    assert _clean_line("*a, b*") == "a, b"
    assert _clean_line("「a、b」") == "a、b"
    # 未装饰的术语列表与词中分隔符/下划线不能被误伤
    assert _clean_line("梯度下降、反向传播、Adam") == "梯度下降、反向传播、Adam"
    assert _clean_line("x_0, x_1") == "x_0, x_1"
    assert _clean_line("*args, **kwargs") == "args, kwargs"
    # 清洗必须是不动点
    for src in ("**卷积**、**池化**、**全连接**", "*fast*, *slow*",
                "*a, b*", "*args, **kwargs"):
        w = _clean_line(src)
        assert w is not None
        assert _clean_line(w) == w, w


def test_words_clean_strips_numbering_of_each_segment():
    """分隔符分隔的带序号词表每一项都要剥掉序号（含装饰）。

    回归：LLM 常输出 "1. **卷积**、2. **池化**、3. **全连接**" 这类编号
    词表；只剥整行行首的序号时后续项残留 "2. **池化**"，且末项的收尾
    装饰符被整行 rstrip 剥掉、前段却保留，词库混入不对称残片
    （"卷积、2. **池化**、3. **全连接"）。中文编号 "1、卷积、2、池化"
    的序号分隔符与术语分隔符同为 "、"，分段后序号单独成段，也要按纯
    数字不是术语的既有规则连同相邻分隔符丢弃。
    """
    assert _clean_line("1. 卷积、2. 池化、3. 全连接") == "卷积、池化、全连接"
    assert _clean_line("1. **卷积**、2. **池化**、3. **全连接**") \
        == "卷积、池化、全连接"
    assert _clean_line("（1）卷积、（2）池化") == "卷积、池化"
    assert _clean_line("(1) 卷积, (2) 池化") == "卷积, 池化"
    assert _clean_line("1) 卷积; 2) 池化; 3) 全连接") == "卷积; 池化; 全连接"
    assert _clean_line("1、卷积、2、池化、3、全连接") == "卷积、池化、全连接"
    assert _clean_line("1、卷积；2、池化") == "卷积；池化"
    assert _clean_line("卷积、2、池化") == "卷积、池化"
    # 序号与装饰头相邻：必须先把成对装饰剥掉再剥序号，否则 "*" 被列表
    # 符号规则吃掉、收尾符失去配对成为残片（"卷积、*池化**"）
    assert _clean_line("1. **卷积**、2. **池化**") == "卷积、池化"
    assert _clean_line("1. 卷积**、2. 池化") == "卷积、池化"
    # 小数/版本号等真实术语不能被序号规则误伤
    assert _clean_line("2.5D、0.5倍速") == "2.5D、0.5倍速"
    assert _clean_line("3.14、2.718") == "3.14、2.718"
    # 清洗必须是不动点
    for src in ("1. **卷积**、2. **池化**", "1、卷积、2、池化",
                "（1）卷积、（2）池化"):
        w = _clean_line(src)
        assert w is not None
        assert _clean_line(w) == w, w
