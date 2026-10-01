# topodroid_tdr
Syntax checker for Topodroid .tdr files

Something that got out of hand as it turned out to be a bigger problem than expected.

This is (or will be) part of Troggle [https://expo.survex.com/handbook/troggle/training/trogbegin.htm](https://expo.survex.com/handbook/troggle/trogintro.html#why),
part of the system that manages paperless survey trip 'wallets'. Troggle manages the archive of the 50-year
Cambridge University Caving Club expedition to Austria, mostly in the Schwarzmooskogel System (150+ km).

While PocketTopo, Topodroid and SexyTopo all export survex files and image files, the requirements
of the archive mean that these all need hand-editing to be used in our survey production workflow. 
Post-expo in 2026, troggle started work on making this part of the process a bit easier.

Currently the centreline export from Topodroid to survex and SVG is working (with some rough edges)
but the export of the vector sketches requires parsing of the *.tdr binary files. The centreline is 
already a bit of a pig, with 4 different Topodroid database schemas to be used and applied, but the
TDR format is an order of magnitude worse: currently we are tracking 7 different binary formats across
our archive of 133 Topodroid .tdr files in 29 survey wallets from 2016 to 2026
https://expo.survex.com/paperless#topodroid .

This is not a port or conversion from the Topodroid source code, this is a new implementation working
directly from hexdumps of the tdr files, inspired by what we generally know about what the files contain 
and what topodroid does. It builds on understanding of completed similar work with SexyTopo 
(which is a much cleaner system where vector data is all in JSON, like its centreline data). It does
not attempt to cover all Topodroid versions: we are only concerned with our own archived data. 
These are the 133 TDR files in our archive with version number and number of TDR files at that version:
|Version |No. of files|
|--------|--------|
|602012 |2|
|602011 |2|
|501040 |13|
|401092 |9|
|400020 |3|
|301040 |104|

(The most recent surveys in 2026 use version 501040 i.e. 5.1.40, because Frank's phone can't upgrade to a more recent version of Topodroid.) 
This is not the final word on the versions in use as we have some survey trips identified as paperless but where we do not yet
have the original source data uploaded to troggle: https://expo.survex.com/paperless#missing .

The Troggle code is all available at https://expo.survex.com/repositories/troggle/.git/ under the MIT
license. A good starting point which imports all the bits is https://expo.survex.com/repositories/troggle/.git/tree/core/views/topodroid.py .

The Topodroid source has been consulted for inspiration but this has often
turned out to be misleading, especially when dealing with 10-year old data constructed by old versions.
Gemini and Copilot have been extensively used in chat mode to work with the hexdumps and 
to spit out code fragments.

### Current status
At the time of creating this repo on GitHub, the code parses and reads the headers of all files but fails to interpret the 
geometry features on any except for v3.1.40, and most of the feature tags are not yet identified. Just checking the format 
of the geometric scraps requires actually parsing them properly. So at this point the project aim is changing from being 
a format checker to becoming a full parser-converter-SVGexporter. The code architecture is being refactored to match this new direction. 

