from micras_pcb import sexpr


def test_spans_allow_byte_exact_edits():
    text = '(a (b "x y") (c 1 2)\n\t(d "q\\"r"))'
    root = sexpr.parse(text)
    c = root.child("c")
    assert text[c.start : c.end] == "(c 1 2)"
    assert root.child("d").atoms() == ['q"r']
    assert sexpr.splice(text, [(c.start, c.end, "(c 3)")]) == '(a (b "x y") (c 3)\n\t(d "q\\"r"))'


def test_fmt():
    assert sexpr.fmt(100.0) == "100"
    assert sexpr.fmt(-0.0000001) == "0"
    assert sexpr.fmt(95.4928932) == "95.492893"
