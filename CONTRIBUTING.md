# Contributing / Como contribuir

Thanks for helping! / Obrigado por ajudar! (Português abaixo.)

## English

1. **Fork** the repository and create a branch (`fix/ctr-region`, `feature/smb`).
2. Set up: `.\scripts\setup_dev.ps1`, then `.\scripts\run.ps1` to start the app.
3. Keep business rules out of the interface: `core.py`, `convert.py`, `vmc.py`, `fixes.py` have no Qt code.
4. Add or update tests and run `.venv\Scripts\python.exe -m pytest -q`. Tests must only use temporary folders and
   fake files — never a real USB drive.
5. Interface texts go to `src/pops_manager/i18n.py` in **Portuguese, English and Spanish**.
6. Open a **pull request** to `main`. Direct pushes to `main` are blocked; the `tests` check must pass and the
   maintainer reviews every PR.

**Never commit** games, BIOS, `POPS_IOX.PAK`, `POPSTARTER.ELF`, `.irx` drivers, fix packs or other third-party
binaries. The CI fails if such files are added. If a change affects what is written to the device, describe how you
tested it on a PS2 (model, OPL/POPStarter version, device, file system) and update `docs/COMPATIBILITY.md`.

### Releases (maintainer)

1. Update `version` in `pyproject.toml` and `src/pops_manager/__init__.py`, merge to `main`.
2. Create and push a tag with the same version: `git tag v0.3.0` and `git push origin v0.3.0`.
3. The *Release* workflow builds the public Windows version, runs the tests and the smoke test, and publishes
   `POPS-Manager-<version>-win64.zip` on the Releases page.

## Português

1. Faça um **fork** do repositório e crie um branch (`fix/ctr-regiao`, `feature/smb`).
2. Ambiente: `.\scripts\setup_dev.ps1` e depois `.\scripts\run.ps1` para abrir o programa.
3. Regras de negócio ficam fora da interface: `core.py`, `convert.py`, `vmc.py` e `fixes.py` não usam Qt.
4. Crie ou atualize testes e rode `.venv\Scripts\python.exe -m pytest -q`. Os testes usam apenas pastas temporárias
   e arquivos falsos — nunca um pendrive de verdade.
5. Textos da interface vão em `src/pops_manager/i18n.py` em **português, inglês e espanhol**.
6. Abra um **pull request** para o `main`. Push direto no `main` é bloqueado; o check `tests` precisa passar e
   o mantenedor revisa todo PR.

**Nunca envie** jogos, BIOS, `POPS_IOX.PAK`, `POPSTARTER.ELF`, drivers `.irx`, pacotes de correções ou outros
binários de terceiros. A CI falha se esses arquivos forem adicionados. Se a mudança altera o que é gravado no
dispositivo, conte como testou no PS2 (modelo, versão do OPL/POPStarter, dispositivo, sistema de arquivos) e
atualize o `docs/COMPATIBILITY.md`.
