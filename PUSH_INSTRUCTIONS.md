# Push to GitHub — steps to run on your machine

The repo is fully assembled with git history already committed (8 commits on
`main`). You just add your remote and push. I can't push for you — that needs
your GitHub credentials, which stay with you.

## 1. Unpack

```bash
tar -xzf yks-radar-repo.tar.gz
cd yks-radar-repo
git log --oneline        # sanity check: 8 commits, newest first
```

## 2. Create the empty GitHub repo

On github.com, create a new **empty** repository (no README, no .gitignore, no
license — this repo already has them). Name it e.g. `yks-radar-institutional`.
Copy its URL.

## 3. Add the remote and push

HTTPS:
```bash
git remote add origin https://github.com/<you>/yks-radar-institutional.git
git push -u origin main
```

SSH:
```bash
git remote add origin git@github.com:<you>/yks-radar-institutional.git
git push -u origin main
```

## 4. Verify

```bash
cd backend
python -m pip install -e ".[dev]"
pytest                              # expect 41 passed
python -m yks_institutional.demo    # end-to-end sanity run
```

## Notes

- **Private repo recommended** — this is proprietary product IP.
- `.gitignore` already blocks real student data (`*.xlsx`, `*.csv`, `*.sqlite3`,
  `/data/`, `/uploads/`) with test fixtures excepted. Keep real school files
  outside the repo or in an ignored `/data/` folder.
- If your org uses a default branch other than `main`, rename before pushing:
  `git branch -m main <name>`.
