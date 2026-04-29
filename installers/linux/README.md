To generate and run the AppImage from the repo root:

```sh
sudo apt-get update
sudo apt-get install -y curl libfuse2t64
chmod +x installers/linux/build_linux.sh
./installers/linux/build_linux.sh
chmod +x installers/linux/out/gbccs-x86_64.AppImage
./installers/linux/out/gbccs-x86_64.AppImage
```

On distributions that still package FUSE 2 as `libfuse2`, install that package instead
of `libfuse2t64`.
