## Contributing (code) to Skepticoin

Thanks for contributing to Skepticoin!

(This guide is work in progress; you may be unlucky enough to remind me of some principle which I'll then add only after
your PR is rejected)

* Use GitHub's PRs to send patches.
* Try to mirror the idiom of the surrounding code, even if you don't like it.
* New functionality should have tests. (scripts / examples may be exempt).
* Make sure the tests pass. Locally, this can be done with:

```
PYTHONPATH=. pytest tests
```

* flake8 (configured in `tox.ini`) is used as a linter. You can run this with:

```
flake8
```

* Both `flake8` and the tests will be automatically run as a Github action for PRs and on master.

* Commits should correspond to some logical unit of change. Not too small, not too big.
* Write meaningful commit messages (but there is no grammatical or syntactical pattern that you must follow)
