# cop4710

[Brainstorm Doc](https://fsu-my.sharepoint.com/:w:/r/personal/csm21e_fsu_edu/_layouts/15/Doc.aspx?sourcedoc=%7B4B8CB7F9-3CAF-44DA-A7F9-B190912E027F%7D&file=Project_drafting.docx&wdLOR=c57684336-0F58-5740-AA0A-FAD63D08B57D&fromShare=true&action=default&mobileredirect=true)

# Set up (for mac OS)

1. install homebrew (if not already installed)
```shell
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

2. install Selenium
```shell
brew install selenium-server
```
When this gets installed you may run into security issues with mac, to bypass:
`Settings -> Privacy & Security (scroll down) -> Selenium should be there, click open anyways`

3. in a .venv, install remaining dependencies
```shell
pip install pycryptodome
pip install flask
pip install werkzeug
```

Should run but lmk if it doesn't
