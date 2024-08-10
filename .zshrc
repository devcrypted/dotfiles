## ZSH DEFAULT CONFIG
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="robbyrussell"

# List of plugins can be found here https://github.com/ohmyzsh/ohmyzsh/wiki/Plugins
plugins=(git ansible asdf aws azure bun cp dnf docker docker-compose gh git golang helm httpie istioctl kind kubectl kubectx minikube mongocli npm nvm pep8 pip pipenv poetry pyenv ssh tmux ufw vagrant virtualenv vscode yarn)
source $ZSH/oh-my-zsh.sh

## CUSTOM USER CONFIG
alias tf=terraform
alias k=kubectl
alias p=poetry
alias n=npm