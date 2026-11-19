import json
from pathlib import Path
import sys

import pytest

FERRAMENTAS = Path(__file__).resolve().parent.parent
TESTES = Path(__file__).resolve().parent
sys.path.insert(0, str(FERRAMENTAS))
sys.path.insert(0, str(TESTES))


@pytest.fixture(scope="session")
def clipe(tmp_path_factory):
    """O clipe sintético, gerado uma vez por rodada de testes."""
    import gerar_clipe
    return gerar_clipe.gerar(tmp_path_factory.mktemp("clipe"))


@pytest.fixture
def dados_teste():
    return TESTES / "dados"


@pytest.fixture
def estado_fixo():
    """Estado de um vídeo com caminhos fixos (não precisa dos arquivos): base do teste de regressão do XML."""
    return json.loads((TESTES / "dados" / "estado_fixo.json").read_text(encoding="utf-8"))
