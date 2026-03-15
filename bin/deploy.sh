rm -r build
rm -r dist
rm -r mdfile.egg-info

python setup.py sdist bdist_wheel
twine upload --config-file .pypirc dist/*