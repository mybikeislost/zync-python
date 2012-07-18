# ZYNC Python API

## Usage

```python
import zync

# authenticate with ZYNC and define which app you'll be submitting with
z = zync.Zync('username', 'password', app='nuke', 'http://zync')

# add a mapping to translate default OSX network paths to /mnt (which zync defaults to)
z.add_path_mapping('/Volumes', '/mnt')

# supply some non-default rendering paramters
params = dict(frange='1-100',
              chunk_size=2)
# submit the job to ZYNC
z.submit('/path/to/nuke_script.nk', 'write_node', params)

# get info on jobs
jobs = z.list(max=10)
for job in jobs:
    print job.params()
    job.cancel()
```

## Dependencies

This library uses [httplib2](http://code.google.com/p/httplib2/).

It is included with this API for convenience, though you can also install it with `pip` or `easy_install`:

```
easy_install httplib2
```

