#!/bin/bash
cd "$(dirname "$0")"
git pull --quiet
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 collecter_urgences.py
git add data/
git diff --staged --quiet || { git commit -m "Relevé urgences $(date '+%Y-%m-%d %H:%M')"; git push --quiet; }