#!/bin/sh

set -e

root=$(pwd)

mkdir -p $root/build/native

if [ ! -d $root/sleef-native ]; then
    cd $root/build/native
    mkdir -p sleef
    cd sleef
    export CC= CXX=
    cmake $root/third_party/sleef -DBUILD_LIBM=OFF -DBUILD_DFT=OFF -DBUILD_QUAD=OFF -DBUILD_GNUABI_LIBS=OFF -DBUILD_TESTS=OFF
    make -j$(nproc) mkalias mkdisp mkmasked_gnuabi mkrename mkrename_gnuabi
    mkdir -p $root/sleef-native/bin
    cp -v bin/* $root/sleef-native/bin
fi

if [ ! -d $root/protobuf-native ]; then
    cd $root/third_party/protobuf
    sh ./autogen.sh
    cd $root/build/native
    mkdir -p protobuf 
    cd protobuf
    export CC= CXX=
    $root/third_party/protobuf/configure --prefix=$root/protobuf-native CFLAGS="-fuse-ld=bfd" CXXFLAGS="-fuse-ld=bfd" LDFLAGS="-Wl,-fuse-ld=bfd"
    make -j$(nproc)
    make install
fi

if [ x$MXE != x ]; then
    if [ x$1 = x64 ]; then
        blas_dir=$root/third_party/openblas/x86_64-w64-mingw32
        build_dir=$root/build/x86_64-w64-mingw32
        cmake_command=x86_64-w64-mingw32.shared-cmake
        pkg_suffix=x64
    else
        blas_dir=$root/third_party/openblas/i686-w64-mingw32
        build_dir=$root/build/i686-w64-mingw32
        cmake_command=i686-w64-mingw32.shared-cmake
        pkg_suffix=x86
    fi
else
    case "$HOST" in
        i686-w64-mingw32)
            toolchain=/usr/win32-toolchain.cmake
            pkg_suffix=x64
            ;;
        x86_64-w64-mingw32)
            toolchain=/usr/win64-toolchain.cmake
            pkg_suffix=x86
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

make -j$(nproc) torch_cpu torch torch_global_deps

for dir in . caffe2 ; do
    cmake -DCMAKE_INSTALL_LOCAL_ONLY=TRUE -DCMAKE_INSTALL_PREFIX=$(pwd)/dist -P $dir/cmake_install.cmake
done

for dir in confu-deps/cpuinfo confu-deps/FP16 caffe2/onnx/torch_ops third_party/fmt c10 sleef caffe2/aten caffe2/core caffe2/serialize caffe2/utils caffe2/perfkernels caffe2/contrib caffe2/predictor caffe2/predictor/emulator caffe2/core/nomnigraph caffe2/db caffe2/distributed caffe2/ideep caffe2/image caffe2/video caffe2/mobile caffe2/mpi caffe2/observers caffe2/onnx caffe2/opt caffe2/proto caffe2/python caffe2/queue caffe2/sgd caffe2/share caffe2/transforms ; do
    cmake -DCMAKE_INSTALL_PREFIX=$(pwd)/dist -P $dir/cmake_install.cmake
done

for comp in libprotobuf protobuf-headers protobuf-protos protobuf-export ; do
    cmake -DCMAKE_INSTALL_COMPONENT=$comp -DCMAKE_INSTALL_PREFIX=$(pwd)/dist -P third_party/protobuf/cmake/cmake_install.cmake
done

tar -czvf libtorch-$pkg_suffix.tar.gz --transform 's/^dist/libtorch/' dist/
