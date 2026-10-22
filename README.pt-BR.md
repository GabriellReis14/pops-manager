<p align="center"><img src="src/pops_manager/assets/icon.png" width="96" alt="Ícone do POPS Manager"></p>

# POPS Manager

[English](README.md) · **Português**

Ferramenta livre para Windows que prepara jogos de PS1 para **POPStarter + OPL (menu Apps)** em pendrive ou HD externo, num passo só: converte para VCD, copia, cria o lançador do OPL, as memory cards, os arquivos de multidisco e as correções dos jogos.

Ela substitui o `PS1_USB_Converter.exe`, o `VMC and MultiDisc Creator.exe` e um conversor de VCD (PSXVCD/CUE2POPS), reproduzindo a saída deles byte a byte (veja [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md), em inglês). Testada num PS2 Slim com OPL e POPStarter r13. Nenhum jogo ou binário de terceiros do POPStarter é fornecido.

## Download

1. Abra a página de [**Releases**](../../releases/latest) e baixe o `POPS-Manager-<versão>-win64.zip`.
2. Extraia para um caminho curto (ex.: `C:\POPS-Manager`) e abra o `POPS-Manager.exe` (Windows 10/11 64 bits).
3. Coloque os seus arquivos do POPStarter (veja [Arquivos do POPStarter](#arquivos-do-popstarter)).

O Windows SmartScreen pode avisar sobre "editor desconhecido", porque o executável não tem assinatura digital: clique em *Mais informações → Executar assim mesmo*, ou compile você mesmo a partir do código.

## Funções

- Adicione jogos de qualquer pasta (botão ou arrastar e soltar): `.VCD`, `.CUE` + `.BIN` (também um `.bin` por faixa), `.BIN`/`.ISO`/`.IMG` brutos, `.ZIP` e `.7Z`.
- Conversão para VCD (idêntica byte a byte ao PSXVCD) numa pasta temporária, apagada no final. Até 3 jogos são convertidos **em paralelo** enquanto o atual é gravado; a gravação é feita um jogo por vez para não fragmentar os VCDs. A barra mostra velocidade e tempo restante, e avisa quando o próprio dispositivo é lento.
- Status e progresso por jogo; ao cancelar, os jogos concluídos são mantidos; um jogo com erro não interrompe os outros.
- Antes de gravar, mostra em árvore como o destino vai ficar (novo / mantido / conflito).
- Lançador no menu Apps do OPL (`APPS/XX.<ID>/`) com nomes completos e legíveis (`Tony_Hawks_Pro_Skater_2`, até 48 caracteres), ou nomes curtos de 22 caracteres como o conversor original — sem a colisão dele em *Tony Hawk's Pro Skater 2/3/4*.
- **Correções dos jogos**: com o pacote *Hugopocked POPStarter Fixes*, cada jogo recebe automaticamente as suas correções (`CHEATS.TXT`, `PATCH_n.BIN`, `TROJAN_n.BIN`, reconhecidas por nome, região e versão). A janela *Correções...* permite escolher variantes (16:9…), modos de compatibilidade, correções gerais ou arquivos seus.
- Memory cards vazias (`SLOT0/1.VMC`) e multidisco (`DISCS.TXT`/`VMCDIR.TXT`), também como ferramenta separada para jogos que já estão no dispositivo.
- Copia o conteúdo da sua pasta `POPS` (`POPS_IOX.PAK`, `CHEATS.TXT`, `IGR_*.TM2`…) quando ainda não existe no destino.
- *Ferramentas → Verificar dispositivo*: modelo, sistema de arquivos, MBR/GPT, cluster/setor, **fragmentação dos VCDs** e aviso de **gabinete NVMe** (somente leitura).
- Nunca sobrescreve nada no dispositivo. Interface em português, inglês e espanhol.

## Como usar

1. **Adicionar jogos** (ou arraste arquivos/pastas para a janela). Arquivos que não podem ser usados mostram **✖ Erro** — passe o mouse para ver o motivo; eles são ignorados.
2. Se quiser, edite o nome no OPL e o identificador (letras, números e `_`, até 48). Confira a coluna **Correções**; clique duas vezes nela para mudar as correções de um jogo.
3. Escolha o **destino** (raiz do pendrive/HD). Confira a árvore: verde = novo, cinza = já existe e será mantido, vermelho = conflito.
4. Confira a linha **Arquivos POPStarter** (✔ = encontrado) e as opções de VMC / multidisco.
5. Clique em **Preparar PS2**, confirme e acompanhe o progresso de cada jogo.
6. Se um jogo não abrir, use *Ferramentas → Verificar dispositivo* e leia [Dispositivos compatíveis](#dispositivos-compatíveis).

Resultado no dispositivo:

```
RAIZ_DO_USB/
├── APPS/
│   ├── XX.Tony_Hawks_Pro_Skater_2/
│   │   ├── XX.Tony_Hawks_Pro_Skater_2.ELF   cópia do POPSTARTER.ELF
│   │   └── title.cfg                        title=Tony Hawk's Pro Skater 2 / boot=XX.Tony_Hawks_Pro_Skater_2.ELF
│   ├── XX.D1_Final_Fantasy_VII/ …
│   └── XX.D2_Final_Fantasy_VII/ …
└── POPS/
    ├── POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2  da sua pasta POPS, só se ainda não existirem
    ├── Tony_Hawks_Pro_Skater_2.VCD
    ├── Tony_Hawks_Pro_Skater_2/  SLOT0.VMC, SLOT1.VMC, CHEATS.TXT, PATCH_1.BIN, TROJAN_0.BIN …  (cards + correções)
    ├── D1_Final_Fantasy_VII.VCD, D2_Final_Fantasy_VII.VCD
    ├── D1_Final_Fantasy_VII/  SLOT0.VMC, SLOT1.VMC, DISCS.TXT, VMCDIR.TXT
    └── D2_Final_Fantasy_VII/  DISCS.TXT, VMCDIR.TXT  (saves compartilhados com o disco 1)
```

Os VCDs não podem ir para uma pasta por jogo: o POPStarter descobre o VCD pelo nome do próprio ELF e só procura em `POPS/` (ou `POPS0`…`POPS9`). Todo o resto de cada jogo fica na pasta `POPS/<ID>/`, e o lançador em `APPS/XX.<ID>/`.

## Dispositivos compatíveis

### Evite SSD NVMe em gabinete USB (ex.: Realtek RTL9210)

Um SSD NVMe num gabinete USB com ponte **Realtek RTL9210**, formatado corretamente em FAT32, **mostra os jogos no OPL, mas todo jogo do POPStarter pisca a tela e volta para o OPL**. Os mesmos arquivos abrem normalmente num pendrive comum e num HD de 2,5" em gabinete SATA. Todo o resto era idêntico (VCDs, lançadores, arquivos do POPStarter, partição, sem fragmentação).

Por quê: o OPL lê o dispositivo com o driver dele, que já está funcionando. Ao abrir um jogo, o POPStarter reinicia o processador de entrada/saída do PS2 e carrega os drivers USB de novo, então o dispositivo precisa ser reconhecido uma segunda vez. Gabinetes NVMe consomem mais energia do que a porta USB do PS2 fornece (500 mA) e demoram a responder depois desse reinício; o POPStarter não encontra o VCD e volta para o OPL.

O que fazer:

- Prefira **pendrive** ou **HD/SSD SATA em gabinete USB** (pontes JMicron ou ASMedia SATA funcionaram).
- Se quiser tentar um gabinete NVMe mesmo assim, ligue-o com **cabo Y** (as duas portas USB do PS2) ou por um **hub USB com fonte própria**.
- *Ferramentas → Verificar dispositivo* mostra o modelo do dispositivo e avisa sobre pontes NVMe (RTL9210/RTL9220, JMS581/JMS583, ASM2362/ASM2364/ASM2464).

### Sistema de arquivos, partição e fragmentação

- **FAT32** é o padrão do POPStarter. Para discos acima de 32 GB, a janela de formatação do Windows só oferece NTFS/exFAT; versões recentes do Windows 11 formatam FAT32 maior pelo terminal (`format X: /FS:FAT32 /Q`), e formatadores de terceiros também funcionam. O resultado foi verificado e está correto.
- **exFAT** só funciona com os drivers do **BDMAssault** (El_Isra) instalados no **Memory Card** como `mc0:/POPSTARTER/usbd.irx` e `usbhdfsd.irx`. O POPStarter r13 não carrega esses drivers do pendrive/HD, então uma pasta `POPSTARTER` no dispositivo não tem efeito (o POPS Manager não a copia, a menos que você ative).
- Com o BDMAssault no Memory Card, um pendrive **GPT** também funcionou. Sem ele, use MBR.
- Cada VCD precisa estar **num bloco contínuo**. VCD fragmentado é outra causa clássica de "pisca e volta para o OPL". *Verificar dispositivo* lista os VCDs fragmentados; copie tudo para um dispositivo recém-formatado (ou desfragmente).

## Velocidade

O lado do PC é rápido (um jogo de 660 MB converte em poucos segundos, e os próximos são convertidos enquanto o atual é gravado). O limite costuma ser o dispositivo: pendrives USB 2.0 gravam em geral de 5 a 20 MB/s, então um jogo de 700 MB pode levar um minuto ou mais. Gravar vários jogos ao mesmo tempo não seria mais rápido e fragmentaria os VCDs.

## Arquivos do POPStarter

O POPS Manager precisa do `POPSTARTER.ELF` e normalmente do `POPS_IOX.PAK`. **Eles não estão neste repositório nem nas releases**: o POPStarter é freeware de código fechado e o `POPS_IOX.PAK` contém o emulador POPS da Sony. Use as suas cópias. Coloque-as numa pasta `resources` ao lado do `POPS-Manager.exe`, com a mesma estrutura do dispositivo, ou escolha em *Configurações → Arquivos do POPStarter*:

```
resources/POPS/POPSTARTER.ELF, POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2 …
resources/POPS/POPSUtils/          opcional: Hugopocked POPStarter Fixes
resources/POPSTARTER/…             opcional; normalmente fica no Memory Card
```

Ordem de busca: *Configurações* → arquivos embutidos num build pessoal → `resources` ao lado do exe → a raiz do projeto, quando roda pelo código-fonte. Programas Windows da pasta POPS (`.exe`, `.dll`) não são copiados, a menos que você ative. Patches de imagem (`.xdelta`/`.ppf`) do pacote de correções precisam ser aplicados à imagem manualmente (ex.: com o DeltaPatcher); a janela *Correções...* indica onde estão.

## Rodar pelo código-fonte

```powershell
.\scripts\setup_dev.ps1     # cria a .venv e instala o projeto + ferramentas (usa o uv se estiver instalado)
.\scripts\run.ps1           # abre o programa (funciona de qualquer diretório)
.venv\Scripts\python.exe -m pytest -q
```

Python 3.10+ (testado no 3.10 e no 3.14). No VS Code, escolha a `.venv` como interpretador; *Run and Debug → POPS Manager* e o painel de testes já estão configurados.

## Compilar

```powershell
.\scripts\build_windows.ps1                    # testes, build do PyInstaller (pasta), teste de inicialização do exe
.\scripts\build_windows.ps1 -Zip               # também gera dist\POPS-Manager-<versão>-win64.zip (o mesmo das Releases)
.\scripts\build_windows.ps1 -BundleResources   # build PESSOAL com seus arquivos POPS, POPSTARTER\ e correções embutidos
```

O build pessoal grava `PERSONAL_BUILD_DO_NOT_DISTRIBUTE.txt`: **nunca publique nem compartilhe** (o `-Zip` é recusado nele). As releases são geradas pelo GitHub Actions a partir de uma tag de versão, sem nenhum arquivo de terceiros. O ícone é uma arte original desenhada por `scripts/make_icon.py`.

## Créditos

O POPS Manager se apoia no trabalho da cena de PS2. Ele reimplementa, com código próprio, o comportamento de:

- **POPStarter** — krHACKen (documentação de Shaolin Assassin)
- **CUE2POPS** — krHACKen (formato VCD)
- **PS1 USB / SMB Mass Converter Tool** e **VMC and MultiDisc Creator** — Eliminator14
- **Title-CFG Maker** e **BDMAssault** — El_Isra (israpps)
- **POPStarter Fixes** — Hugopocked (correções por jogo, usadas a partir da sua cópia do pacote)
- **PSXVCD** — conversor de VCD usado como referência pela comunidade
- **Open PS2 Loader** — ps2homebrew / equipe do OPL

Bibliotecas: Qt for Python/PySide6 (LGPLv3), py7zr (LGPL-2.1); PyInstaller para os builds. A mesma lista está em *Ajuda → Sobre e créditos*. PlayStation é marca registrada da Sony Interactive Entertainment; este projeto não tem ligação com a Sony.

## Como contribuir

Pull requests são bem-vindos — veja [CONTRIBUTING.md](CONTRIBUTING.md). Em issues, inclua o relatório de *Verificar dispositivo*, a versão do programa, a versão do OPL/POPStarter e o que aconteceu. Nunca anexe jogos, BIOS ou binários proprietários de terceiros.

## Situação

- ✅ Testado no PS2: VCDs convertidos, lançador do OPL, nomes completos, correções dos jogos
- ✅ Saída idêntica ao PS1_USB_Converter, ao VMC and MultiDisc Creator e ao PSXVCD (sem as colisões de nome deles)
- ✅ Conversão em paralelo, progresso por jogo, velocidade/tempo restante, cancelar, nunca sobrescrever; verificação do dispositivo
- ⏳ Modo SMB, cópia que desfragmenta, arquivos compactados com vários discos

Copyright © colaboradores. Código original do projeto sob licença MIT; nenhum direito reivindicado sobre POPStarter, OPL ou as ferramentas citadas.
