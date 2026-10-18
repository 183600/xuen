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


def test_words_clean_unwraps_multiple_pairs_in_one_word():
    """同一行里被连接词/空格隔开的多组装饰对必须连配对一起剥干净。

    回归：只从词头 unwrap 时，第二组装饰的收尾符会被整行 rstrip 当边缘
    字符剥掉、开头的装饰符却留在词中（"**备忘**和**结论**" ->
    "备忘和**结论"），残片随词库进入每轮提示词；连续引语
    "「注意」与「记忆」" 也会留下 "注意」与「记忆" 这类不对称残片。
    完整成对（同字符、同数量）的装饰要连配对一起剥。
    """
    assert _clean_line("**前置**和**后置**") == "前置和后置"
    assert _clean_line("**A**、**B** 和 **C**") == "A、B 和 C"
    assert _clean_line("**A**和**B**和**C**") == "A和B和C"
    assert _clean_line("*a* or *b*") == "a or b"
    assert _clean_line("`code` and `more`") == "code and more"
    assert _clean_line("「注意」与「记忆」") == "注意与记忆"
    assert _clean_line("“生成模型”与“判别模型”") == "生成模型与判别模型"
    assert _clean_line("**术语**（解释）与**别的**（解释2）") \
        == "术语（解释）与别的（解释2）"
    assert _clean_line("（**重点**）") == "（重点）"
    assert _clean_line("！**重点**！") == "！重点"
    # 不能误伤：没有配对或词中是乘号/星号记号/撇号时原样保留
    assert _clean_line("2**10") == "2**10"
    assert _clean_line("C*代数") == "C*代数"
    assert _clean_line("C*代数与D*几何") == "C*代数与D*几何"
    assert _clean_line("a*b*c") == "a*b*c"
    assert _clean_line("m*n*k") == "m*n*k"
    assert _clean_line("don't panic") == "don't panic"
    assert _clean_line("Newton's method") == "Newton's method"
    assert _clean_line("x_0, x_1") == "x_0, x_1"
    # 真实词表端到端：多组装饰/引语同行时残片不能混进词库
    assert parse_word_lines("- **注意力**和**记忆**\n“卷积”与“池化”\n") \
        == ["注意力和记忆", "卷积与池化"]
    # 清洗必须是不动点
    for src in ("**前置**和**后置**", "「注意」与「记忆」",
                "“生成模型”与“判别模型”", "**A**、**B** 和 **C**"):
        w = _clean_line(src)
        assert w is not None
        assert _clean_line(w) == w, w


def test_words_clean_unwraps_multiple_single_char_quote_pairs():
    """单字内容的连续引语对必须各自完整剥掉，不能并成一对留下残片。

    回归：引号对内容若允许跨过自己的收尾符，可选组的贪婪匹配会先吃掉
    真正的收尾符、再一路滑到行内最后一个同类收尾符——"「a」和「b」"
    被当成一对剥出 "a」和「b"（收尾符残片留在词中），"『x』与『y』"、
    "“a”和“b”"、「甲」与「乙」同理；残片随词库进入每轮提示词。
    """
    assert _clean_line("「a」和「b」") == "a和b"
    assert _clean_line("『x』与『y』") == "x与y"
    assert _clean_line("“a”和“b”") == "a和b"
    assert _clean_line("‘a’与‘b’") == "a与b"
    assert _clean_line("「甲」与「乙」") == "甲与乙"
    assert _clean_line("《A》与《B》") == "A与B"
    assert _clean_line("【A】和【B】") == "A和B"
    assert _clean_line("〔x〕与〔y〕") == "x与y"
    assert _clean_line("〖a〗与〖b〗") == "a与b"
    # 多对连排、被其他文字包裹时同样不能并对
    assert _clean_line("「a」和「b」和「c」") == "a和b和c"
    assert _clean_line("A「x」B「y」C") == "AxByC"
    assert _clean_line("（「x」与「y」）") == "（x与y）"
    # 多字内容与强调对不受影响
    assert _clean_line("「注意」与「记忆」") == "注意与记忆"
    assert _clean_line("**A**和**B**") == "A和B"
    assert _clean_line('"a" and "b"') == "a and b"
    # 真实词表端到端：单字引语残片不能混进词库
    assert parse_word_lines("- 「a」和「b」\n") == ["a和b"]
    # 清洗必须是不动点
    for src in ("「a」和「b」", "『x』与『y』", "“a”和“b”", "A「x」B「y」C"):
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


def test_words_clean_keeps_terms_with_tight_ascii_separators():
    """数字前缀 + 紧贴的 ASCII 逗号/分号不是列表序号，术语不能被截断。

    回归：纯数字段被当列表序号丢弃时只看分隔符分段，未区分分隔符类型。
    "1,2-丙二醇" 被截成 "2-丙二醇"、"2,4-D" 被截成 "4-D"、"1,25-二羟基
    维生素D3" 被截成 "25-二羟基维生素D3"——词形变成另一个术语（1,2-丙二醇
    与 2-丙二醇是不同化合物），词库进入每轮提示词后会误导外部 agent。
    紧贴数字的 ASCII 逗号/分号是术语内部连接符（列表序号常见写法
    "1. " / "1) " / "1、" 已由 _BULLET 与顿号规则处理）；分隔符后跟空白
    （"1, 卷积"）或使用中文顿号（"1、卷积"）时仍按列表序号剥掉。
    """
    # 化学名/版本号：紧贴的 ASCII 逗号在术语内部
    assert _clean_line("1,2-丙二醇") == "1,2-丙二醇"
    assert _clean_line("2,3-二甲基丁烷") == "2,3-二甲基丁烷"
    assert _clean_line("1,3,5-三嗪") == "1,3,5-三嗪"
    assert _clean_line("1,25-二羟基维生素D3") == "1,25-二羟基维生素D3"
    assert _clean_line("2,4-D") == "2,4-D"
    # 术语后面还有列表时也不受影响
    assert _clean_line("2,3-二甲基丁烷、乙醇") == "2,3-二甲基丁烷、乙醇"
    # 不能借机放宽真正的列表序号：带空白 / 中文顿号仍要剥
    assert _clean_line("1, 卷积") == "卷积"
    assert _clean_line("1, 卷积, 2, 池化") == "卷积, 池化"
    assert _clean_line("1、卷积、2、池化") == "卷积、池化"
    # 真实词表端到端：被截断的词不能混进词库
    assert parse_word_lines("1,2-丙二醇\n2,4-D\n") == ["1,2-丙二醇", "2,4-D"]
    # 清洗必须是不动点
    for src in ("1,2-丙二醇", "1,3,5-三嗪", "2,4-D", "1, 卷积, 2, 池化"):
        w = _clean_line(src)
        assert w is not None
        assert _clean_line(w) == w, w


def test_words_clean_rejects_fullwidth_colon_urls():
    """全角冒号 URL 不能截出协议名残片混进词库。

    回归：URL 拦截只匹配半角 "://"，中文语料常见的 "http：//example.com"
    （全角冒号）绕过检查、落到冒号截断逻辑，协议名 "http"/"https"/"ftp"
    被当作词头留下，随灵感词拼进每轮提示词——这正是 URL 检查要拦的行为。
    """
    assert _clean_line("http：//example.com") is None
    assert _clean_line("https：//example.com/a/b") is None
    assert _clean_line("ftp：//files.example.com") is None
    assert _clean_line("HTTP：//example.com") is None
    # URL 前后还有解释文字时同样整行丢弃（半角冒号 URL 即如此）
    assert _clean_line("见 http：//example.com 的说明") is None
    # 不能误伤正常的冒号解释截断
    assert _clean_line("损失函数：交叉熵") == "损失函数"
    assert _clean_line("_grad_accum：梯度累积") == "grad_accum"
    # 端到端：协议名不能混进词库
    assert parse_word_lines(
        "http：//example.com\nalpha\nhttps：//x.org\nbeta\n") == ["alpha", "beta"]
