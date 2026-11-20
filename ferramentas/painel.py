#!/usr/bin/env python3
"""Painel de revisão no navegador: assistir ao corte, apontar ajustes e aprovar.

Uso (a pasta do vídeo primeiro):
  painel.py abrir <pasta> [--porta 8765] [--navegador] [--ocioso 120]
      sobe o painel em http://127.0.0.1:<porta>/?t=<token> e fica rodando até Ctrl+C
      (ou até --ocioso minutos sem a página aberta). Só aceita conexões desta máquina.
  painel.py previas <pasta> [--todas]
      gera as prévias leves das mídias que o navegador não toca (ProRes, HEVC, áudio
      PCM em MOV), da voz tratada e das animações com transparência
  painel.py verificar <pasta>
      o que o navegador toca direto e o que precisa de prévia (sem gerar nada)
  painel.py boas-vindas <pasta> [--porta 8765] [--navegador] [--ocioso 60]
      o começo de um vídeo novo pelo navegador: verificação, briefing, tipo de vídeo, estilo e
      padrão de legenda (com prévia). Ao enviar, grava no estado e em _CLAUDE/briefing_painel.md,
      mostra o resumo em JSON e termina (código 0). Fechado sem enviar: código 3.

No painel: o vídeo toca já cortado, com as animações, a legenda e o som; o roteiro
mostra o que saiu do corte (riscado) e deixa cortar ou devolver frases; os pedidos
viram pendências no estado (_CLAUDE/projeto.json), que o Claude aplica na etapa.
"""
from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
from pathlib import Path
import secrets
import shutil
import socketserver
import sys
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edicao import boas_vindas as BV  # noqa: E402
from edicao import estado as E  # noqa: E402
from edicao import painel as P  # noqa: E402

WEB = Path(__file__).resolve().parent / "painel_web"
TIPOS = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".mp4": "video/mp4",
         ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".mkv": "video/x-matroska",
         ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
         ".ogg": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".jpg": "image/jpeg",
         ".png": "image/png"}
BLOCO = 256 * 1024


class Painel:
    def __init__(self, pasta: str, token: str | None = None, modo: str = "painel"):
        self.pasta = str(Path(pasta).resolve())
        E.ler(self.pasta)  # falha cedo se o vídeo não foi iniciado
        self.token = token or secrets.token_urlsafe(18)
        self.fila = P.Fila(self.pasta)
        self.ultimo_acesso = time.monotonic()
        self.porta = None
        self.modo = modo            # "painel" ou "boas_vindas"
        self.enviado = None         # o resumo, quando as boas-vindas forem enviadas
        self.fim = threading.Event()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "PainelEdicao/1"
    painel: Painel  # posto pela fábrica

    def log_message(self, *a):  # silencioso: o navegador pede pedaços de vídeo o tempo todo
        pass

    # ------------------------------------------------------------ utilitários
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        p = self.painel.porta
        return host in (f"127.0.0.1:{p}", f"localhost:{p}", f"[::1]:{p}")

    def _token_ok(self, q: dict) -> bool:
        t = self.headers.get("X-Painel-Token") or (q.get("t") or [None])[0]
        return bool(t) and secrets.compare_digest(t, self.painel.token)

    def _json(self, obj, status=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, status, msg, **extra):
        self._json({"erro": msg, **extra}, status)

    def _arquivo(self, arq: Path, cache: bool = False):
        tam = arq.stat().st_size
        tipo = TIPOS.get(arq.suffix.lower()) or mimetypes.guess_type(arq.name)[0] or "application/octet-stream"
        ini, fim = 0, tam - 1
        faixa = self.headers.get("Range")
        status = 200
        if faixa and faixa.startswith("bytes="):
            a, _, b = faixa[6:].split(",")[0].strip().partition("-")
            try:
                if a:
                    ini = int(a)
                    fim = min(int(b), tam - 1) if b else tam - 1
                else:  # sufixo: os últimos N bytes
                    ini = max(0, tam - int(b))
            except ValueError:
                ini, fim = 0, tam - 1
            if ini >= tam or ini > fim:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{tam}")
                self.end_headers()
                return
            status = 206
        n = fim - ini + 1
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(n))
        if status == 206:
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{tam}")
        self.send_header("Cache-Control", "private, max-age=3600" if cache else "no-cache")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(arq, "rb") as f:
            f.seek(ini)
            while n > 0:
                pedaco = f.read(min(BLOCO, n))
                if not pedaco:
                    break
                self.wfile.write(pedaco)
                n -= len(pedaco)

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            raise P.ErroPainel("pedido grande demais")
        return json.loads(self.rfile.read(n) or b"{}")

    # ------------------------------------------------------------ GET
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._get()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # o navegador cancelou um pedaço de vídeo (normal ao pular no tempo)

    def _get(self):
        if not self._host_ok():
            return self._erro(403, "endereço não permitido")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        caminho = unquote(u.path)
        self.painel.ultimo_acesso = time.monotonic()
        if caminho in ("/", "/index.html"):
            return self._arquivo(WEB / ("boas-vindas.html" if self.painel.modo == "boas_vindas" else "index.html"))
        if caminho.startswith("/web/"):
            alvo = (WEB / caminho[5:]).resolve()
            if WEB.resolve() not in alvo.parents or not alvo.is_file():
                return self._erro(404, "não encontrado")
            return self._arquivo(alvo)
        if not self._token_ok(q):
            return self._erro(401, "token inválido: abra o endereço que o painel mostrou no terminal")
        if caminho == "/api/boas-vindas":
            return self._json(BV.opcoes(self.painel.pasta))
        if caminho == "/api/exemplo.jpg":
            try:
                arq = BV.quadro_exemplo(self.painel.pasta)
            except Exception as e:  # noqa: BLE001 (ffmpeg não leu o arquivo)
                return self._erro(500, str(e))
            return self._arquivo(arq) if arq else self._erro(404, "sem gravações ainda")
        if caminho.startswith("/api/previa-tema/"):
            partes = caminho.split("/")
            arq = BV.previa_tema(partes[3], partes[4]) if len(partes) == 5 else None
            return self._arquivo(arq, cache=True) if arq else self._erro(404, "sem prévia")
        if caminho == "/api/dados":
            return self._json(P.dados(self.painel.pasta))
        if caminho == "/api/revisao":
            d = E.ler(self.painel.pasta)
            return self._json({"revisao": d.get("revisao"), "previas": self.painel.fila.estado()})
        if caminho == "/api/previas":
            return self._json(self.painel.fila.estado())
        if caminho.startswith("/arquivo/"):
            arq = P.arquivo(self.painel.pasta, caminho[len("/arquivo/"):])
            if not arq or not arq.exists():
                return self._erro(404, "mídia indisponível")
            return self._arquivo(arq)
        if caminho == "/api/miniatura":
            try:
                arq = P.miniatura(self.painel.pasta, q["video"][0], float(q["tempo"][0]))
            except (KeyError, ValueError, E.ErroEstado) as e:
                return self._erro(404, str(e))
            except Exception as e:  # noqa: BLE001 (ffmpeg não conseguiu tirar o quadro)
                return self._erro(500, str(e))
            return self._arquivo(arq, cache=True)
        return self._erro(404, "não encontrado")

    # ------------------------------------------------------------ POST
    def do_POST(self):
        try:
            self._post()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _post(self):
        if not self._host_ok():
            return self._erro(403, "endereço não permitido")
        u = urlparse(self.path)
        if not self._token_ok(parse_qs(u.query)) or not self.headers.get("X-Painel-Token"):
            return self._erro(401, "token inválido")
        self.painel.ultimo_acesso = time.monotonic()
        pasta = self.painel.pasta
        try:
            c = self._corpo()
            rev = c.get("revisao")
            acao = u.path
            if acao == "/api/cortes":
                P.editar_cortes(pasta, rev, c["acao"], **{k: v for k, v in c.items() if k not in ("acao", "revisao")})
            elif acao == "/api/cortes/desfazer":
                P.desfazer_cortes(pasta, rev)
            elif acao == "/api/pedido":
                P.novo_pedido(pasta, rev, c.get("etapa"), c.get("texto"), c.get("item"), c.get("tempo_seq"),
                              bool(c.get("aprendizado")))
            elif acao == "/api/pedido/resolver":
                P.resolver_pedido(pasta, rev, c["id"])
            elif acao == "/api/motion":
                P.status_motion(pasta, rev, c["id"], c["status"], c.get("texto"), bool(c.get("aprendizado")))
            elif acao == "/api/etapa/aprovar":
                P.aprovar_etapa(pasta, rev, c["etapa"])
            elif acao == "/api/legenda":
                P.corrigir_legenda(pasta, c["id"], c["texto"])
            elif acao == "/api/previas":
                return self._json(self.painel.fila.iniciar(bool(c.get("todas"))))
            elif acao == "/api/boas-vindas":
                resumo = BV.salvar(pasta, c)
                self.painel.enviado = resumo
                threading.Timer(1.5, self.painel.fim.set).start()  # a página recebe a resposta antes de fechar
                return self._json({"ok": True, "resumo": resumo})
            else:
                return self._erro(404, "ação desconhecida")
        except E.Conflito as e:
            return self._erro(409, str(e), dados=P.dados(pasta))
        except (E.ErroEstado, BV.C.ErroConfig, KeyError, ValueError, TypeError) as e:
            msg = f"faltou o campo {e}" if isinstance(e, KeyError) else str(e)
            return self._erro(400, msg)
        return self._json({"ok": True, "dados": P.dados(pasta)})


class Servidor(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def criar_servidor(pasta: str, porta: int = 0, token: str | None = None,
                   modo: str = "painel") -> tuple[Servidor, Painel]:
    painel = Painel(pasta, token, modo)
    h = type("H", (Handler,), {"painel": painel})
    srv = Servidor(("127.0.0.1", porta), h)
    painel.porta = srv.server_address[1]
    return srv, painel


def cmd_abrir(a):
    srv, painel = criar_servidor(a.pasta, a.porta)
    url = f"http://127.0.0.1:{painel.porta}/?t={painel.token}"
    print(f"Painel de revisão: {url}", flush=True)
    print("(só desta máquina; Ctrl+C para fechar)", flush=True)
    if a.navegador:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        while t.is_alive():
            time.sleep(1)
            if a.ocioso and time.monotonic() - painel.ultimo_acesso > a.ocioso * 60:
                print(f"fechado depois de {a.ocioso} min sem a página aberta", flush=True)
                break
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    return 0


def cmd_boas_vindas(a):
    srv, painel = criar_servidor(a.pasta, a.porta, modo="boas_vindas")
    url = f"http://127.0.0.1:{painel.porta}/?t={painel.token}"
    print(f"Boas-vindas: {url}", flush=True)
    print("(só desta máquina; termina sozinho quando a pessoa enviar)", flush=True)
    if a.navegador:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        while not painel.fim.wait(1):
            if a.ocioso and time.monotonic() - painel.ultimo_acesso > a.ocioso * 60:
                break
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    if painel.enviado:
        print("ENVIADO " + json.dumps(painel.enviado, ensure_ascii=False), flush=True)
        return 0
    print("fechado sem enviar: nada foi gravado", flush=True)
    return 3


def cmd_verificar(a):
    d = P.dados(a.pasta)
    for chave, m in d["midias"].items():
        if not m["usado"]:
            continue
        if m["url"]:
            extra = f" ({m['aviso']})" if m["aviso"] else ""
            print(f"{chave}: toca ({m['fonte']}){extra}")
        else:
            print(f"{chave}: precisa de prévia ({m['motivo']})" if m["precisa_previa"] else f"{chave}: {m['motivo']}")
    print(f"prévias faltando: {d['previas_faltando']}")
    return 0


def cmd_previas(a):
    tarefas = P.tarefas_previa(a.pasta, a.todas)
    if not tarefas:
        print("nada a gerar: o navegador já toca tudo")
        return 0
    largura = shutil.get_terminal_size((80, 20)).columns
    for t in tarefas:
        def prog(x, t=t):
            print(f"\r{t['chave']}: {x * 100:5.1f}%".ljust(min(40, largura)), end="", flush=True)
        arq = P.gerar_previa(a.pasta, t, prog)
        print(f"\r{t['chave']}: {arq} ({t['motivo']})".ljust(min(40, largura)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("abrir"); p.add_argument("pasta"); p.add_argument("--porta", type=int, default=8765)
    p.add_argument("--navegador", action="store_true", help="abre o navegador padrão")
    p.add_argument("--ocioso", type=float, default=120, help="minutos sem a página aberta até fechar (0 = nunca)")
    p.set_defaults(f=cmd_abrir)
    p = sub.add_parser("previas"); p.add_argument("pasta"); p.add_argument("--todas", action="store_true")
    p.set_defaults(f=cmd_previas)
    p = sub.add_parser("verificar"); p.add_argument("pasta"); p.set_defaults(f=cmd_verificar)
    p = sub.add_parser("boas-vindas"); p.add_argument("pasta"); p.add_argument("--porta", type=int, default=8765)
    p.add_argument("--navegador", action="store_true", help="abre o navegador padrão")
    p.add_argument("--ocioso", type=float, default=60, help="minutos sem a página aberta até fechar (0 = nunca)")
    p.set_defaults(f=cmd_boas_vindas)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return a.f(a)
    except OSError as e:
        if getattr(e, "errno", None) in (48, 98, 10048):
            print(f"erro: a porta {a.porta} já está em uso (outro painel aberto?); use --porta 0 para uma livre",
                  file=sys.stderr)
            return 2
        raise
    except E.ErroEstado as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
