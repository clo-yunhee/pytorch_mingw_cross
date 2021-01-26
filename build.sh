#!/bin/sh

set -e

root=$(pwd)

mkdir -p $root/build/native
cd $root/build/native

if [ ! -d $root/sleef-native ]; then
    mkdir -p sleef
    cd sleef
    cmake $root/third_party/sleef -DBUILD_LIBM=OFF -DBUILD_DFT=OFF -DBUILD_QUAD=OFF -DBUILD_GNUABI_LIBS=OFF -DBUILD_TESTS=OFF
    make -j$(nproc) mkalias mkdisp mkmasked_gnuabi mkrename mkrename_gnuabi
    mkdir -p $root/sleef-native/bin
    cp -v bin/* $root/sleef-native/bin
fi

cd $root/build/native

if [ ! -d $root/protobuf-native ]; then
    mkdir -p protobuf 
    cd protobuf
    $root/third_party/protobuf/configure --prefix=$root/protobuf-native CFLAGS="-fuse-ld=bfd" CXXFLAGS="-fuse-ld=bfd" LDFLAGS="-Wl,-fuse-ld=bfd"
    make -j$(nproc)
    make install
fi

if [ x$MXE != x ]; then
    if [ x$1 = x64 ]; then
        blas_dir=$root/third_party/openblas/x86_64-w64-mingw32
        build_dir=$root/build/x86_64-w64-mingw32
        cmake_command=x86_64-w64-mingw32.shared-cmake
    else
        blas_dir=$root/third_party/openblas/i686-w64-mingw32
        build_dir=$root/build/i686-w64-mingw32
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

cmake_args="-DNATIVE_BUILD_DIR=$root/sleef-native -DCAFFE2_CUSTOM_PROTOC_EXECUTABLE=$root/protobuf-native/bin/protoc -DWITH_BLAS=open -DGLIBCXX_USE_CXX11_ABI=1 -DCMAKE_C_FLAGS=-D_WIN32_WINNT=_WIN32_WINNT_WIN7 -DCMAKE_CXX_FLAGS=-D_WIN32_WINNT=_WIN32_WINNT_WIN7"

mkdir -p $build_dir
cd $build_dir
$cmake_command $root $cmake_args || true
$cmake_command $root $cmake_args

make -j$(nproc) torch_cpu

cmake -DCMAKE_INSTALL_LOCAL_ONLY=TRUE -DCMAKE_INSTALL_PREFIX=$(pwd)/dist -P caffe2/cmake_install.cmake
