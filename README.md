# ds1000z-tools

faster data export for rigol ds1000z oscilloscopes

![oscilloscope screenshot and a plotted spectrogram](doc/header.png)

This package contains tools for downloading data and screenshots from rigol
DS1000Z series oscilloscopes over a network. Features:

- save data (both on-screen, and the full memory depth) to numpy data files (.npy)

- save screenshots in PNG format

- reliable and fast auto-discovery (does not use zeroconf)

- It's not slower than it should be -- screenshots take 1 second, saving the full memory takes 30 seconds

## Usage

```bash
# save screen, automatic filename
ds1000z-tools save-screen
# specify filename
ds1000z-tools save-screen screenshot.png

# save full data, automatic filename
ds1000z-tools save-data
# specify filename
ds1000z-tools save-data data.npy
# save on-scren data
ds1000z-tools save-data --screen  # or -s
# save specific channels
ds1000z-tools save-data --channels 1,3  # or -c

# specify host to connect to
ds1000z-tools --address scope.lan save-data  # or -a
```
