"""FCP 7 XML (xmeml v4): a entrega para o Premiere (e o Resolve, que também lê).

O que sai:
- V1 câmera (os segmentos do corte), V3 animações em tela cheia, V4 sobreposições;
- A1 a voz, como par estéreo "explodido" com as marcas do Premiere
  (totalExplodedTrackCount, premiereTrackType, premiereChannelType),
  ligado ao vídeo do mesmo take;
- as trilhas abaixo: efeitos sonoros, com ganho em dB;
- fades de áudio: crossfade centrado de 2 frames nas junções da voz e 1 frame
  no começo e no fim (start-black / end-black), como em entrega-no-editor.md;
- marcadores da sequência.

Regra do fluxo: o primeiro arquivo de um formato novo é um teste curto que a
pessoa abre e confere (montar(..., teste=True)). Atributos específicos do
Premiere (cor de marcador, por exemplo) são copiados de um XML exportado por ele.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import quote, unquote, urlparse
import uuid as _uuid
from xml.sax.saxutils import escape

from .tempo import Taxa

CROSSFADE = {"name": "Cross Fade (+3dB)", "effectid": "KGAudioTransCrossFade3dB"}
TRILHA_TELA_CHEIA = 3
TRILHA_SOBREPOSICAO = 4


class ErroXML(Exception):
    pass


# --------------------------------------------------------------- caminhos
def pathurl(caminho: str) -> str:
    """Caminho absoluto → file://localhost/… (Windows: file://localhost/C:/…)."""
    texto = str(caminho)
    if re.match(r"^[A-Za-z]:[\\/]", texto):
        p = PureWindowsPath(texto).as_posix()
        return "file://localhost/" + quote(p, safe="/:")
    if not texto.startswith("/"):
        texto = str(Path(texto).resolve())
    return "file://localhost" + quote(texto, safe="/")


def caminho_de_url(url: str) -> str:
    u = urlparse(url)
    p = unquote(u.path)
    if re.match(r"^/[A-Za-z]:/", p):
        p = p[1:]
    return p


# --------------------------------------------------------------- modelo
@dataclass
class Midia:
    id: str
    caminho: str
    duracao: float                 # segundos
    largura: int | None = None
    altura: int | None = None
    canais: int = 2                # canais de áudio (0 = sem áudio)
    tem_video: bool = True
    alpha: bool = False


@dataclass
class Clipe:
    midia: Midia
    in_f: int
    out_f: int
    start: int
    tipo: str                      # "video" | "audio"
    trilha: int                    # vídeo: índice da trilha; áudio: trilha lógica (par estéreo)
    grupo: int | None = None       # clipes do mesmo take (vídeo + áudio) ficam ligados
    ganho_db: float | None = None
    nome: str | None = None
    # preenchidos na montagem
    ids: list[str] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.start + self.out_f - self.in_f


@dataclass
class Marcador:
    frame: int
    nome: str
    comentario: str = ""
    cor_premiere: int | None = None  # valor de <pproColor>, copiado de um XML exportado pelo Premiere


class Sequencia:
    def __init__(self, nome: str, taxa, largura: int, altura: int, taxa_audio: int = 48000,
                 fade_frames: int = 1, menos_um: bool = False) -> None:
        self.nome = nome
        self.taxa = Taxa.de(taxa)
        self.largura, self.altura = largura, altura
        self.taxa_audio = taxa_audio
        self.fade = fade_frames
        # menos_um: bordas de clipe dentro de transição escritas como -1 (a forma
        # da especificação FCP7). Padrão: o valor real do corte.
        self.menos_um = menos_um
        self.clipes: list[Clipe] = []
        self.marcadores: list[Marcador] = []
        self.avisos: list[str] = []
        self._grupo = 0

    def novo_grupo(self) -> int:
        self._grupo += 1
        return self._grupo

    def f(self, s: float) -> int:
        return self.taxa.frames(s)

    def adicionar(self, clipe: Clipe) -> Clipe:
        dur_f = self.f(clipe.midia.duracao)
        if clipe.out_f <= clipe.in_f:
            raise ErroXML(f"clipe vazio em {clipe.midia.id} ({clipe.in_f}–{clipe.out_f})")
        if clipe.in_f < 0 or clipe.out_f > dur_f + 1:
            raise ErroXML(f"{clipe.midia.id}: {clipe.in_f}–{clipe.out_f} fora do arquivo (0–{dur_f} frames)")
        self.clipes.append(clipe)
        return clipe

    # --------------------------------------------------------- serialização
    def _trilhas(self):
        vid: dict[int, list[Clipe]] = {}
        aud: dict[int, list[Clipe]] = {}
        for c in self.clipes:
            (vid if c.tipo == "video" else aud).setdefault(c.trilha, []).append(c)
        for d, nome in ((vid, "V"), (aud, "A")):
            for t, cs in d.items():
                cs.sort(key=lambda c: c.start)
                for a, b in zip(cs, cs[1:]):
                    if b.start < a.end:
                        raise ErroXML(f"clipes sobrepostos em {nome}{t}: {a.midia.id}@{a.start} e {b.midia.id}@{b.start}")
        return vid, aud

    def _itens_audio(self, cs: list[Clipe], cruzar: bool) -> list[dict]:
        """Clipes de uma trilha de áudio com as transições (fades).

        `cruzar`: junções coladas ganham crossfade (a voz). Nas outras trilhas,
        cada clipe tem fade de entrada e de saída próprio.
        """
        itens: list[dict] = []
        n = len(cs)
        fade = self.fade
        # cruza[i]: junção entre cs[i] e cs[i+1] ganha crossfade centrado. Precisa
        # de `fade` frames de mídia sobrando em cada lado; sem isso, cada lado
        # ganha o seu fade de 1 frame (melhor que um corte seco, que estala).
        cruza = []
        for i in range(n - 1):
            a, b = cs[i], cs[i + 1]
            colado = cruzar and fade and a.end == b.start
            sobra = a.out_f + fade <= self.f(a.midia.duracao) and b.in_f - fade >= 0
            if colado and not sobra:
                self.avisos.append(f"junção em {a.end}: sem mídia sobrando para o crossfade "
                                   f"({a.midia.id} → {b.midia.id}); fade de saída e de entrada no lugar")
            cruza.append(bool(colado and sobra))
        for i, c in enumerate(cs):
            ini, fim = c.start, c.end
            junta_ant = i > 0 and cruza[i - 1]
            junta_prox = i < n - 1 and cruza[i]
            if fade and not junta_ant:
                d = min(fade, (fim - ini) // 2)
                if d:
                    itens.append({"tr": True, "start": ini, "end": ini + d, "align": "start-black"})
                    ini = self._borda(ini)
            elif fade and junta_ant:
                ini = self._borda(ini)  # a transição já foi posta pelo clipe anterior
            itens.append({"clipe": c, "start": ini, "end": fim})
            if fade and junta_prox:
                itens[-1]["end"] = self._borda(fim)
                itens.append({"tr": True, "start": c.end - fade, "end": c.end + fade, "align": "center"})
            elif fade:
                d = min(fade, (c.end - c.start) // 2)
                if d:
                    itens[-1]["end"] = self._borda(fim)
                    itens.append({"tr": True, "start": c.end - d, "end": c.end, "align": "end-black"})
        return itens

    def _borda(self, valor: int) -> int:
        return -1 if self.menos_um else valor

    def xml(self) -> str:
        vid, aud = self._trilhas()
        n_vid = max(vid) if vid else 1
        n_aud = max(aud) if aud else 1
        cid = 0
        trilhas_v: list[list[dict]] = []
        for t in range(1, n_vid + 1):
            trilhas_v.append([{"clipe": c, "start": c.start, "end": c.end} for c in vid.get(t, [])])
        # cada trilha lógica de áudio vira 2 trilhas no XML (canal 1 e 2)
        trilhas_a: list[list[dict]] = []
        for t in range(1, n_aud + 1):
            base = self._itens_audio(aud.get(t, []), cruzar=(t == 1))
            for canal in (1, 2):
                trilhas_a.append([dict(it, canal=canal) for it in base])

        # ids e índices (o índice conta clipes E transições da trilha)
        posicao: dict[tuple[int, int], tuple[str, int, int]] = {}  # (id(clipe), canal) → (clipitem id, trilha xml, índice)
        for tv, itens in enumerate(trilhas_v, start=1):
            for k, it in enumerate(itens, start=1):
                cid += 1
                it["id"] = f"clipitem-{cid}"
                posicao[(id(it["clipe"]), 0)] = (it["id"], tv, k)
        for ta, itens in enumerate(trilhas_a, start=1):
            for k, it in enumerate(itens, start=1):
                if it.get("tr"):
                    continue
                cid += 1
                it["id"] = f"clipitem-{cid}"
                posicao[(id(it["clipe"]), it["canal"])] = (it["id"], ta, k)

        grupos: dict[int, list[tuple[str, str, int, int, int]]] = {}
        for c in self.clipes:
            if c.grupo is None:
                continue
            if c.tipo == "video":
                pid, tr, idx = posicao[(id(c), 0)]
                grupos.setdefault(c.grupo, []).append((pid, "video", tr, idx, 0))
            else:
                for canal in (1, 2):
                    pid, tr, idx = posicao[(id(c), canal)]
                    grupos.setdefault(c.grupo, []).append((pid, "audio", tr, idx, canal))

        arquivos_declarados: set[str] = set()
        fid: dict[str, str] = {}
        for c in self.clipes:
            if c.midia.caminho not in fid:
                fid[c.midia.caminho] = f"file-{len(fid) + 1}"

        rate = self._rate()
        dur_seq = max([c.end for c in self.clipes] + [0])
        o: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE xmeml>", '<xmeml version="4">',
                        f'  <sequence id="sequence-1">',
                        f"    <uuid>{_uuid.uuid5(_uuid.NAMESPACE_URL, self.nome)}</uuid>",
                        f"    <duration>{dur_seq}</duration>", f"    {rate}",
                        f"    <name>{escape(self.nome)}</name>", "    <media>", "      <video>",
                        "        <format>", "          <samplecharacteristics>", f"            {rate}",
                        f"            <width>{self.largura}</width>", f"            <height>{self.altura}</height>",
                        "            <anamorphic>FALSE</anamorphic>",
                        "            <pixelaspectratio>square</pixelaspectratio>",
                        "            <fielddominance>none</fielddominance>",
                        "          </samplecharacteristics>", "        </format>"]
        for itens in trilhas_v:
            o.append("        <track>")
            for it in itens:
                o += self._clipitem(it, "video", fid, arquivos_declarados, grupos, None)
            o += ["          <enabled>TRUE</enabled>", "          <locked>FALSE</locked>", "        </track>"]
        o += ["      </video>", "      <audio>", "        <numOutputChannels>2</numOutputChannels>",
              "        <format>", "          <samplecharacteristics>", "            <depth>16</depth>",
              f"            <samplerate>{self.taxa_audio}</samplerate>", "          </samplecharacteristics>",
              "        </format>"]
        for n, itens in enumerate(trilhas_a):
            canal = n % 2 + 1
            o.append(f'        <track currentExplodedTrackIndex="{canal - 1}" totalExplodedTrackCount="2" '
                     f'premiereTrackType="Stereo">')
            for it in itens:
                if it.get("tr"):
                    o += self._transicao(it)
                else:
                    o += self._clipitem(it, "audio", fid, arquivos_declarados, grupos, canal)
            o += ["          <enabled>TRUE</enabled>", "          <locked>FALSE</locked>",
                  f"          <outputchannelindex>{canal}</outputchannelindex>", "        </track>"]
        o += ["      </audio>", "    </media>",
              "    <timecode>", f"      {rate}", "      <string>00:00:00:00</string>", "      <frame>0</frame>",
              "      <displayformat>NDF</displayformat>", "    </timecode>"]
        for m in sorted(self.marcadores, key=lambda m: m.frame):
            o += ["    <marker>", f"      <comment>{escape(m.comentario)}</comment>",
                  f"      <name>{escape(m.nome)}</name>", f"      <in>{m.frame}</in>", "      <out>-1</out>"]
            if m.cor_premiere is not None:
                o.append(f"      <pproColor>{m.cor_premiere}</pproColor>")
            o.append("    </marker>")
        o += ["  </sequence>", "</xmeml>", ""]
        return "\n".join(o)

    def _rate(self) -> str:
        return (f"<rate><timebase>{self.taxa.timebase}</timebase>"
                f"<ntsc>{'TRUE' if self.taxa.ntsc else 'FALSE'}</ntsc></rate>")

    def _file(self, m: Midia, fid: dict, declarados: set) -> list[str]:
        ident = fid[m.caminho]
        if ident in declarados:
            return [f'            <file id="{ident}"/>']
        declarados.add(ident)
        rate = self._rate()
        o = [f'            <file id="{ident}">', f"              <name>{escape(Path(m.caminho).name)}</name>",
             f"              <pathurl>{escape(pathurl(m.caminho))}</pathurl>", f"              {rate}",
             f"              <duration>{self.f(m.duracao)}</duration>",
             "              <timecode>", f"                {rate}", "                <string>00:00:00:00</string>",
             "                <frame>0</frame>", "                <displayformat>NDF</displayformat>",
             "              </timecode>", "              <media>"]
        if m.tem_video:
            o += ["                <video>", "                  <samplecharacteristics>", f"                    {rate}",
                  f"                    <width>{m.largura or self.largura}</width>",
                  f"                    <height>{m.altura or self.altura}</height>",
                  "                    <anamorphic>FALSE</anamorphic>",
                  "                    <pixelaspectratio>square</pixelaspectratio>",
                  "                    <fielddominance>none</fielddominance>",
                  "                  </samplecharacteristics>", "                </video>"]
        if m.canais:
            o += ["                <audio>", "                  <samplecharacteristics>",
                  "                    <depth>16</depth>",
                  f"                    <samplerate>{self.taxa_audio}</samplerate>",
                  "                  </samplecharacteristics>",
                  f"                  <channelcount>{m.canais}</channelcount>", "                </audio>"]
        o += ["              </media>", "            </file>"]
        return o

    def _clipitem(self, it, tipo, fid, declarados, grupos, canal) -> list[str]:
        c: Clipe = it["clipe"]
        m = c.midia
        attr = ' premiereChannelType="stereo"' if tipo == "audio" else ""
        o = [f'          <clipitem id="{it["id"]}"{attr}>',
             f"            <masterclipid>masterclip-{fid[m.caminho].split('-')[1]}</masterclipid>",
             f"            <name>{escape(c.nome or Path(m.caminho).name)}</name>",
             "            <enabled>TRUE</enabled>",
             f"            <duration>{self.f(m.duracao)}</duration>", f"            {self._rate()}",
             f"            <start>{it['start']}</start>", f"            <end>{it['end']}</end>",
             f"            <in>{c.in_f}</in>", f"            <out>{c.out_f}</out>"]
        if tipo == "video":
            o.append(f"            <alphatype>{'straight' if m.alpha else 'none'}</alphatype>")
        o += self._file(m, fid, declarados)
        if tipo == "audio":
            fonte = 1 if m.canais < 2 else canal
            o += ["            <sourcetrack>", "              <mediatype>audio</mediatype>",
                  f"              <trackindex>{fonte}</trackindex>", "            </sourcetrack>"]
            if c.ganho_db is not None:
                lin = 10 ** (c.ganho_db / 20)
                o += ["            <filter>", "              <effect>", "                <name>Audio Levels</name>",
                      "                <effectid>audiolevels</effectid>",
                      "                <effectcategory>audiolevels</effectcategory>",
                      "                <effecttype>audiolevels</effecttype>",
                      "                <mediatype>audio</mediatype>", "                <parameter>",
                      "                  <parameterid>level</parameterid>", "                  <name>Level</name>",
                      "                  <valuemin>0</valuemin>", "                  <valuemax>3.98109</valuemax>",
                      f"                  <value>{lin:.6f}</value>", "                </parameter>",
                      "              </effect>", "            </filter>"]
        if c.grupo is not None:
            for pid, mt, tr, idx, _canal in grupos[c.grupo]:
                o += ["            <link>", f"              <linkclipref>{pid}</linkclipref>",
                      f"              <mediatype>{mt}</mediatype>", f"              <trackindex>{tr}</trackindex>",
                      f"              <clipindex>{idx}</clipindex>"]
                if mt == "audio":
                    o.append("              <groupindex>1</groupindex>")
                o.append("            </link>")
        o.append("          </clipitem>")
        return o

    def _transicao(self, it) -> list[str]:
        return ["          <transitionitem>", f"            <start>{it['start']}</start>",
                f"            <end>{it['end']}</end>", f"            <alignment>{it['align']}</alignment>",
                f"            {self._rate()}", "            <effect>",
                f"              <name>{CROSSFADE['name']}</name>",
                f"              <effectid>{CROSSFADE['effectid']}</effectid>",
                "              <effectcategory>Dissolve</effectcategory>",
                "              <effecttype>transition</effecttype>", "              <mediatype>audio</mediatype>",
                "            </effect>", "          </transitionitem>"]


# --------------------------------------------------------------- do estado
def _midia_do_estado(a: dict, sondar=None) -> Midia:
    if a.get("duracao") is None and sondar:
        info = sondar(a["caminho"])
        a = {**info, **a, "duracao": info.get("duracao")}
    if a.get("duracao") is None:
        raise ErroXML(f"sem a duração de {a.get('id') or a.get('caminho')}: rode o inventário (midia.py) antes")
    res = a.get("resolucao") or [None, None]
    tipo = a.get("tipo")
    return Midia(id=a.get("id") or Path(a["caminho"]).stem, caminho=a["caminho"], duracao=float(a["duracao"]),
                 largura=res[0], altura=res[1], canais=int(a.get("canais_audio", 2) or 0),
                 tem_video=tipo not in ("audio",), alpha=bool(a.get("alpha")))


def montar(dados: dict, nome: str | None = None, teste: bool = False, sondar=None,
           cores: dict | None = None, fade_frames: int = 1, menos_um: bool = False) -> Sequencia:
    """Monta a sequência a partir do estado do vídeo.

    teste=True: só os 4 primeiros segmentos, um marcador e (se houver) uma animação
    e um efeito sonoro, para a pessoa abrir no programa e conferir o formato.
    `sondar(caminho) -> dict` completa a duração de arquivos que não estão no inventário.
    `cores`: tipo de marcador → valor de pproColor (copiado de um XML do Premiere).
    """
    from .linha import Linha

    midia = dados.get("midia") or {}
    arquivos = {a["id"]: a for a in midia.get("arquivos", [])}
    segs = (dados.get("cortes") or {}).get("segmentos") or []
    if not segs:
        raise ErroXML("o estado não tem cortes.segmentos")
    principal = arquivos.get(midia.get("principal") or segs[0]["video"]) or {}
    fps = midia.get("fps") or principal.get("fps")
    if not fps:
        raise ErroXML("sem a taxa de quadros (midia.fps)")
    res = midia.get("resolucao") or principal.get("resolucao") or [1920, 1080]
    if teste:
        segs = segs[:4]
    linha = Linha(segs, fps)
    seq = Sequencia(nome or dados.get("projeto", "sequencia"), fps, res[0], res[1],
                    fade_frames=fade_frames, menos_um=menos_um)

    cache: dict[str, Midia] = {}

    def m_de(ident: str) -> Midia:
        if ident not in cache:
            if ident not in arquivos:
                raise ErroXML(f"o vídeo '{ident}' dos cortes não está em midia.arquivos")
            cache[ident] = _midia_do_estado(arquivos[ident], sondar)
            fps_arq = arquivos[ident].get("fps")
            if fps_arq and Taxa.de(fps_arq) != seq.taxa:
                seq.avisos.append(f"{ident} está em {fps_arq} fps e a sequência em {seq.taxa}: confira a sincronia")
        return cache[ident]

    for p in linha.pedacos:
        m = m_de(p.video)
        g = seq.novo_grupo()
        seq.adicionar(Clipe(m, p.in_f, p.out_f, p.seq_ini, "video", 1, g))
        if m.canais:
            seq.adicionar(Clipe(m, p.in_f, p.out_f, p.seq_ini, "audio", 1, g))

    marcs = dados.get("marcadores") or []
    for mk in (marcs[:1] if teste else marcs):
        t, pedaco, dentro = linha.origem_para_seq_proximo(mk["video"], mk["tempo"])
        if teste and t >= linha.duracao:
            continue
        comentario = mk["texto"] if dentro else f"{mk['texto']} (trecho fora do corte, origem {mk['tempo']:.2f}s)"
        seq.marcadores.append(Marcador(seq.f(t), f"{mk['id']} {mk['tipo']}", comentario,
                                       (cores or {}).get(mk["tipo"])))

    fim_seq = linha.duracao
    motions = [i for i in (dados.get("motions") or {}).get("itens", [])
               if i.get("status") in ("renderizado", "entregue") and (i.get("render") or {}).get("arquivo")]
    for it in (motions[:1] if teste else motions):
        if it["inicio_seq"] >= fim_seq:
            continue
        trilha = TRILHA_TELA_CHEIA if it.get("formato") == "tela_cheia" else TRILHA_SOBREPOSICAO
        arq = it["render"]["arquivo"]
        info = {"id": it["id"], "caminho": arq, "tipo": "video", "canais_audio": 0,
                "alpha": trilha == TRILHA_SOBREPOSICAO, "duracao": it.get("render", {}).get("duracao")}
        if info["duracao"] is None and not (sondar and Path(arq).exists()):
            # sem o arquivo para medir: a duração planejada (o programa avisa se faltar mídia)
            info["duracao"] = it["fim_seq"] - it["inicio_seq"]
            seq.avisos.append(f"{it['id']}: não achei {arq}; usei a duração planejada")
        m = _midia_do_estado(info, sondar)
        n = seq.f(it["fim_seq"]) - seq.f(it["inicio_seq"])
        n = min(n, seq.f(m.duracao))
        _colocar(seq, Clipe(m, 0, n, seq.f(it["inicio_seq"]), "video", trilha, nome=it["id"]), "video")

    sfx = (dados.get("sfx") or {}).get("itens", [])
    for it in (sfx[:1] if teste else sfx):
        if not it.get("arquivo") or it.get("status") == "riscado" or it["inicio_seq"] >= fim_seq:
            continue
        m = _midia_do_estado({"id": it["id"], "caminho": it["arquivo"], "tipo": "audio",
                              "canais_audio": it.get("canais", 2), "duracao": it.get("duracao")}, sondar)
        in_f = seq.f(it.get("inicio_arquivo", 0.0))
        out_f = seq.f(it["fim_arquivo"]) if it.get("fim_arquivo") else seq.f(m.duracao)
        _colocar(seq, Clipe(m, in_f, out_f, seq.f(it["inicio_seq"]), "audio", 2, ganho_db=it.get("ganho_db"),
                            nome=it["id"]), "audio")
    return seq


def _colocar(seq: Sequencia, c: Clipe, tipo: str) -> None:
    """Põe o clipe na primeira trilha livre a partir da pedida (sem sobrepor)."""
    t = c.trilha
    while True:
        ocupado = any(o.tipo == tipo and o.trilha == t and o.start < c.end and c.start < o.end for o in seq.clipes)
        if not ocupado:
            if t != c.trilha:
                seq.avisos.append(f"{c.nome}: trilha {'V' if tipo == 'video' else 'A'}{c.trilha} ocupada, foi para a {t}")
            c.trilha = t
            seq.adicionar(c)
            return
        t += 1


# --------------------------------------------------------------- a volta
def ler_volta(xml_texto: str, arquivos: list[dict]) -> dict:
    """Lê a sequência que a pessoa exportou do programa e reconstrói os cortes de V1.

    Devolve {"segmentos": [...], "avisos": [...], "marcadores_pessoa": [...]}.
    Avisa (sem tentar resolver) o que estiver fora do modelo.
    """
    import xml.etree.ElementTree as ET

    raiz = ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", xml_texto))
    seqs = raiz.findall(".//sequence")
    if not seqs:
        raise ErroXML("o XML não tem <sequence>")
    seq = seqs[0]
    tb = int(seq.findtext("rate/timebase"))
    ntsc = seq.findtext("rate/ntsc", "FALSE").upper() == "TRUE"
    taxa = Taxa.de(f"{tb * 1000}/1001" if ntsc else str(tb))
    por_caminho = {}
    for a in arquivos:
        por_caminho[_chave_caminho(a["caminho"])] = a["id"]
        if a.get("proxy"):
            por_caminho[_chave_caminho(a["proxy"])] = a["id"]
    urls: dict[str, str] = {}
    for f in raiz.iter("file"):
        if f.get("id") and f.findtext("pathurl"):
            urls[f.get("id")] = f.findtext("pathurl")

    avisos, segs = [], []
    trilhas_v = seq.findall("media/video/track")
    if not trilhas_v:
        raise ErroXML("a sequência não tem trilhas de vídeo")
    v1 = trilhas_v[0]
    if v1.findall("transitionitem"):
        avisos.append(f"V1 tem {len(v1.findall('transitionitem'))} transições de vídeo: ficaram de fora do modelo")
    for n, ci in enumerate(v1.findall("clipitem"), start=1):
        if ci.findtext("enabled", "TRUE").upper() == "FALSE":
            avisos.append(f"clipe {n} de V1 desligado: ignorado")
            continue
        f = ci.find("file")
        url = (f.findtext("pathurl") if f is not None else None) or urls.get(f.get("id") if f is not None else "")
        ident = por_caminho.get(_chave_caminho(caminho_de_url(url))) if url else None
        nome = ci.findtext("name")
        if not ident:
            avisos.append(f"clipe {n} de V1 ({nome}) não é um arquivo conhecido do projeto: ignorado")
            continue
        for eff in ci.iter("effectid"):
            if eff.text and eff.text.lower() in ("timeremap", "speed"):
                avisos.append(f"clipe {n} de V1 ({nome}) tem mudança de velocidade: fora do modelo")
        start, end = int(ci.findtext("start")), int(ci.findtext("end"))
        cin, cout = int(ci.findtext("in")), int(ci.findtext("out"))
        segs.append({"id": f"s{len(segs) + 1:03d}", "video": ident,
                     "inicio": round(taxa.segundos(cin), 4), "fim": round(taxa.segundos(cout), 4),
                     "_seq": (start, end)})
    # L-cut / J-cut: áudio da voz com bordas diferentes do vídeo
    trilhas_a = seq.findall("media/audio/track")
    if trilhas_a:
        bordas_v = {(s["_seq"][0], s["_seq"][1]) for s in segs}
        for ci in trilhas_a[0].findall("clipitem"):
            s, e = int(ci.findtext("start")), int(ci.findtext("end"))
            if s != -1 and e != -1 and (s, e) not in bordas_v:
                if not any(a <= s and e <= b for a, b in bordas_v):
                    avisos.append(f"áudio em {s}–{e} não bate com o vídeo (L-cut/J-cut?): confira à mão")
    for s in segs:
        s.pop("_seq", None)
    marcs = []
    for mk in seq.findall("marker"):
        marcs.append({"frame": int(mk.findtext("in", "0")), "tempo_seq": round(taxa.segundos(int(mk.findtext("in", "0"))), 3),
                      "nome": mk.findtext("name", ""), "comentario": mk.findtext("comment", ""),
                      "cor": mk.findtext("pproColor")})
    return {"fps": str(taxa), "segmentos": segs, "avisos": avisos, "marcadores": marcs}


def _chave_caminho(c: str) -> str:
    return str(c).replace("\\", "/").lower()
