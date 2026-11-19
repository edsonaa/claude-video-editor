from fractions import Fraction

import pytest

from edicao.tempo import Taxa, de_hms, hms


@pytest.mark.parametrize("entrada,esperado", [
    ("29.97", Fraction(30000, 1001)), ("30000/1001", Fraction(30000, 1001)), (29.97, Fraction(30000, 1001)),
    ("29.97002997", Fraction(30000, 1001)), ("23.976", Fraction(24000, 1001)), ("59.94", Fraction(60000, 1001)),
    ("25", Fraction(25)), (30, Fraction(30)), ("24/1", Fraction(24)), ("29,97", Fraction(30000, 1001)),
])
def test_taxa_exata(entrada, esperado):
    assert Taxa.de(entrada).fps == esperado


def test_taxa_invalida():
    with pytest.raises(ValueError):
        Taxa.de("0")


def test_timebase_e_ntsc():
    t = Taxa.de("29.97")
    assert (t.timebase, t.ntsc) == (30, True)
    assert (Taxa.de(25).timebase, Taxa.de(25).ntsc) == (25, False)
    assert Taxa.de("23.976").timebase == 24


def test_2997_nao_e_30():
    # 1 hora de 29,97 tem 107892 frames, não 108000: o erro clássico do descompasso no fim
    assert Taxa.de("29.97").frames(3600) == 107892
    assert Taxa.de(30).frames(3600) == 108000


def test_ida_e_volta_frames():
    t = Taxa.de("29.97")
    for f in (0, 1, 29, 30, 1799, 1800, 17982, 107891):
        assert t.frames(t.segundos(f)) == f


def test_arredonda_para_o_mais_proximo():
    t = Taxa.de(25)
    assert t.frames(0.019) == 0 and t.frames(0.021) == 1 and t.frames(1.0) == 25


@pytest.mark.parametrize("frame,tc", [
    (0, "00:00:00;00"), (1799, "00:00:59;29"), (1800, "00:01:00;02"), (17982, "00:10:00;00"),
    (17981, "00:09:59;29"), (107892, "01:00:00;00"),
])
def test_drop_frame(frame, tc):
    t = Taxa.de("29.97")
    assert t.timecode(frame, drop=True) == tc
    assert t.de_timecode(tc) == frame


def test_drop_frame_ida_e_volta_longa():
    t = Taxa.de("29.97")
    for f in range(0, 200000, 997):
        assert t.de_timecode(t.timecode(f, drop=True)) == f
    t60 = Taxa.de("59.94")
    for f in range(0, 400000, 1999):
        assert t60.de_timecode(t60.timecode(f, drop=True)) == f


def test_nao_drop():
    t = Taxa.de("29.97")
    assert t.timecode(1800) == "00:01:00:00"
    assert t.de_timecode("00:01:00:00") == 1800
    with pytest.raises(ValueError):
        Taxa.de(25).timecode(10, drop=True)


def test_hms():
    assert hms(75.25) == "01:15.25"
    assert hms(3725.5, 1) == "1:02:05.5"
    assert de_hms("1:15.25") == pytest.approx(75.25)
    assert de_hms("01:02:05.5") == pytest.approx(3725.5)
    assert de_hms("12") == 12
