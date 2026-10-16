# CS2 equipment graphics

These are Valve's original white equipment silhouettes extracted from the local
CS2 installation, app 730, build 25738536. They are game assets owned by Valve;
this project does not claim authorship or relicense them as project code.
PROVENANCE.json records the source paths and SHA-256 of every SVG. Both archive
and Panorama DATA CRCs were checked during import. Git preserves their bytes.

Reproduce with `scripts/import_weapon_icons.py --pak <installed pak01_dir.vpk>
--build-id <installed build id>`. The importer reads the game installation and
writes only the specified output folder (default: this folder).

Reports embed only silhouettes needed by their replays, once per HTML document.
No external images are fetched. The exact model is mapped from active item
names, including separate M4A4/M4A1-S and knife models. Unpictured items keep
their text names; they never borrow another gun's image.

Decoder reference: [Panorama DATA implementation](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/Resource/ResourceTypes/Panorama.cs).
