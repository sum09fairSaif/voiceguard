"""One loader per dataset. Each turns a dataset's own labels into manifest rows.

A loader is a module with:
- NAME: the source name, which is also its folder under data/raw/
- load(root): reads the dataset in data/raw/<NAME>/ and returns a list of
  rows with manifest.LABEL_COLUMNS, paths relative to root

To add a dataset, write a module like the others and add it here.
"""

from sources import asvspoof2019_la, common_voice, in_the_wild, team

LOADERS = {
    module.NAME: module
    for module in (asvspoof2019_la, in_the_wild, common_voice, team)
}
