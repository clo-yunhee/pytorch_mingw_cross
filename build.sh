#!/bin/sh

set -e

root=$(pwd)

mkdir -p sleef-native
cd sleef-native
cmake ../third_party/sleef -DCMAKE_INSTALL_PREFIX=$(pwd) -DBUILD_LIBM=OFF -DBUILD_DFT=OFF -DBUILD_QUAD=OFF -DBUILD_GNUABI_LIBS=OFF -DBUILD_TESTS=OFF
make -j$(nproc)

cd $root

mkdir -p protobuf-native 
cd protobuf-native
../third_party/protobuf/configure --prefix=$(pwd)
make -j$(nproc) -C src protoc
make check
make install

cd $root

if [ x$MXE != x ]; then
    if [ x$1 = x64 ]; then
        blas_dir=$root/third_party/openblas/x86_64-w64-mingw32
        build_dir=$root/build-w64
        cmake_command=x86_64-w64-mingw32.shared-cmake
    else
        blas_dir=$root/third_party/openblas/i686-w64-mingw32
        build_dir=$root/build-w32
        cmake_command=i686-w64-mingw32.shared-cmake
    fi
else
    case "$HOST" in
        i686-w64-mingw32)
            toolchain=/usr/win32-toolchain.cmake
            ;;
        x86_64-w64-mingw32)
            toolchain=/usr/win64-toolchain.cmake
            ;;
    esac
    blas_dir=$root/third_party/openblas/$HOST
    build_dir=$root/build/$HOST
    cmake_command="cmake -DCMAKE_TOOLCHAIN_FILE=$toolchain"
fi

export OpenBLAS_HOME=$blas_dir
export PATH=$root/protoc-native/bin:$PATH
export OpenBLAS_HOME=$blas_dir

cmake_args="-DNATIVE_BUILD_DIR=$root/sleef-native -DCAFFE2_CUSTOM_PROTOC_EXECUTABLE=$root/protoc-native/bin/protoc -DWITH_BLAS=open -DGLIBCXX_USE_CXX11_ABI=1"

mkdir -p $build_dir
cd $build_dir
rm -rf *
$cmake_command $root $cmake_args || true
$cmake_command $root $cmake_args
make -j$(nproc)
