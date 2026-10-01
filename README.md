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
(which is a much cleaner system where vector data is all in JSON, like its centreline data). 

The Troggle code is all available at https://expo.survex.com/repositories/troggle/.git/ under the MIT
license.

The Topodroid source has been consulted for inspiration but this has often
turned out to be misleading, especially when dealing with 10-year old data constructed by old versions.
Gemini and Copilot have been extensively used in chat mode to work with the hexdumps and 
to spit out code fragments.
