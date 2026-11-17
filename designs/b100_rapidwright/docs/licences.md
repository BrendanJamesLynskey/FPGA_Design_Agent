# Licences and what is committed (brief 100)

Nothing in this design is a vendor binary or vendor device data. The repository holds only our scripts, RTL, the version pin
(`flow/rapidwright_pin.py`) and run records.

| Item | Where it comes from | Licence (as recorded 2026-11-17) | Committed? |
|---|---|---|---|
| RapidWright framework 2026.1.2 | PyPI wheel `rapidwright` (`pip`), jar `rapidwright-2026.1.2-standalone-lin64.jar` from the AMD RapidWright GitHub release `v2026.1.2-beta`, fetched by the wheel on first import | Apache 2.0 for the framework (RapidSmith lineage Apache 2.0); the "RapidWright API Library" part of the jar is under an AMD (Xilinx) EULA that allows using it to develop, synthesise, test and verify designs for Xilinx devices and bars copying or redistributing it beyond that and decompiling it (`LICENSE.TXT` inside the wheel, sections "RapidWright API Library - Xilinx EULA") | no |
| Device files (`xck26_db.dat`, `xc7a100t_db.dat`, the routing and timing tables) | downloaded by RapidWright on first use from `http://data.rapidwright.io/` (plain HTTP; the downloader checks an md5 file) into `~/.local/share/RapidWright/data` | no separate licence file was found beside the data; they are part of the RapidWright distribution and are treated as covered by the same EULA, so they are never committed or redistributed | no |
| JPype 1.7.1 | PyPI | Apache 2.0 | no |
| Java runtime | the JRE inside Vivado 2026.1 (`.../tps/lnx64/jre24.0.2_12`, Temurin 24.0.2+12) | GPLv2 with Classpath Exception (Temurin); installed with Vivado, not redistributed here | no |
| Vivado 2026.1 | owner's licensed install | AMD | no |

Two clauses worth knowing before reusing results elsewhere (from the EULA text in the wheel, our reading, not legal advice):

- the EULA restricts using "results from benchmarking the Software" for software development other than as the licence permits.
  Our comparisons measure designs placed and routed by Vivado and by RapidWright's router; they are reported as engineering results
  of the flow, with the tool versions and the conditions, and we do not publish them as a benchmark of RapidWright.
- the device files are downloaded over plain HTTP. The downloader validates them against an md5 it also fetches from the same host,
  which is integrity against corruption, not against a hostile network. Our run records state the versions; the files are not hashed
  in the repository because they are not committed.

Project X-Ray / Project U-Ray and nextpnr-xilinx (open place and route, considered and not used: `design.md` section 3.3) are
ISC / Apache 2.0 licensed open-source projects (from memory, unverified); none of their code or data is used here.
