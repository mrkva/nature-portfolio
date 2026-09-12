# Nature portfolio

A static portfolio of iNaturalist photographs, hosted on GitHub Pages.
No build tooling in the browser: `index.html` reads `data/index.json`, which the
GitHub Action generates from the iNaturalist API on every push and daily, at deploy
time.