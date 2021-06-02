## Contributing (code) to Skepticoin

Thanks for contributing to Skepticoin!

(This guide is work in progress; you may be unlucky enough to remind me of some principle which I'll then add only after
your PR is rejected)

* Use GitHub's PRs to send patches.
* Try to mirror the idiom of the surrounding code, even if you don't like it.
* New functionality should have tests. (scripts / examples may be exempt).
* Make sure the tests pass. (Instructions in next section)
* Commits should correspond to some logical unit of change. Not too small, not too big.
* Write meaningful commit messages (but there is no grammatical or syntactical pattern that you must follow)


## Sanity checks

CI runs all these checks to check each PR. To qualify for getting merged, your PR needs to pass all checks.

You can run tests locally with pre-commit hooks, details in the next section.

Our checks are:
* pytest for running tests. Run like this:
```
PYTHONPATH=. pytest tests
```

* flake8 (configured in `tox.ini`) is used as a linter. You can run this with:

```sh
flake8
```

* mypy (configured in `pre-commit-config.yaml`) is used as a type-checker. Run with:

```sh
mypy skepticoin --strict --implicit-reexport --allow-subclassing-any --allow-any-generics --ignore-missing-imports
```

### Setup pre-commit hooks (optional)

Pre-commit hooks are a feature of git that let commands run before a commit happens.
This way we can run `flake8`, `mypy` and the tests, just like they would run on CI, but without pushing.

Pre-commit hooks can be set up like this:
```sh
# Install pre-commit
pip install pre-commit

# Install the hooks from the yaml file
pre-commit install
```

After that the hooks will run automatically on when you run `git commit`.
If a check fails, the commit doesn't go through, so it effectively enforces that the checks pass on new commits.