---
title: Contributing
---

## Contributing

### Code

When contributing to Oras Python, it is important to properly communicate the gist of the contribution. 
If it is a simple code or editorial fix, simply explaining this within the GitHub Pull Request (PR) will suffice. But if this is a larger 
fix or Enhancement, it should be first discussed with the project leader or developers.
You can look at the [OWNERS](https://github.com/oras-project/oras-py/blob/main/OWNERS.md) file of the repository to see who might be best to ping,
or jump into the [#oras](https://cloud-native.slack.com/archives/CJ1KHJM5Z) channel in the
CNCF slack.

Please note that this project has adopted the [CNCF Code of Conduct](https://github.com/cncf/foundation/blob/master/code-of-conduct.md).
Please follow it in all your interactions with the project members and users.

## Pull Request Process

1. All pull requests should go to the main branch.
2. Follow the existing code style precedent. The testing includes linting that will help, but generally we use black, isort, mypy, and pyflakes.
3. Test your PR locally, and provide the steps necessary to test for the reviewers.
4. The project's default copyright and header have been included in any new source files.
5. All (major) changes to Singularity Registry must be documented in the CHANGELOG.md in the root of the repository, and documentation updated here.
6. If necessary, update the README.md.
7. The pull request will be reviewed by others, and the final merge must be done by an OWNER.

If you have any questions, please don't hesitate to [open an issue](https://github.com/oras-project/oras-py/issues).


### Documentation

Want to contribute to the documentation here? Great! You'll need Jekyll and git.

#### Install git

Initially (on OS X), you will need to setup [Brew](http://brew.sh/) which is a package manager for OS X and [Git](https://git-scm.com/). To install Brew and Git, run the following commands:

```bash
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
brew install git
```
If you are on Debian/Ubuntu, then you can easily install git with `apt-get`

```bash
apt-get update && apt-get install -y git
```

#### Install Jekyll

You can also install Jekyll with brew.

```bash
$ brew install ruby
$ gem install jekyll
$ gem install bundler
$ bundle install
```

On Ubuntu I do a different method:

```bash
git clone https://github.com/rbenv/ruby-build.git ~/.rbenv/plugins/ruby-build
echo 'export PATH="$HOME/.rbenv/plugins/ruby-build/bin:$PATH"' >> ~/.bashrc
exec $SHELL
rbenv install 2.3.1
rbenv global 2.3.1
gem install bundler
rbenv rehash
ruby -v

# Rails
curl -sL https://deb.nodesource.com/setup_4.x | sudo -E bash -
sudo apt-get install -y nodejs
gem install rails -v 4.2.6
rbenv rehash

# Jekyll
gem install jekyll
gem install github-pages
gem install jekyll-sass-converter

rbenv rehash
```

#### Get the code

You should first fork the repository to your GitHub organization or username,
and then clone it.

```bash
$ git clone https://github.com/<username>/oras-py.git oras-py
$ cd oras-py/docs
```

### Serve

Depending on how you installed jekyll:

```bash
jekyll serve
# or
bundle exec jekyll serve
```

We will hopefully provide docs preview on Netlify, which is what the other
oras projects use.
