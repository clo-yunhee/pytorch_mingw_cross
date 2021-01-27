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
    bits=${1:-32}
else
    case "$HOST" in
    *i686*)   bits=32 ;;
    *x86_64*) bits=64 ;;
    esac
fi

if [ x$bits = x32 ]; then
    target=i686-w64-mingw32
    build_dir=$root/build/$target
    blas_arch=x86
    pkg_suffix=x86
elif [ x$bits = x64 ]; then
    target=x86_64-w64-mingw32
    build_dir=$root/build/$target
    blas_arch=x86_64
    pkg_suffix=x64
else
    echo "Bits should be 32 or 64!" >&2
    exit 1
fi

if [ x$MXE != x ]; then
    cmake_command=$target.shared-cmake
    cross_fc=$target.shared-gfortran
    cross_cc=$target.shared-gcc
else
    cmake_command="cmake -DCMAKE_TOOLCHAIN_FILE=/usr/win$bits-toolchain.cmake"
    cross_fc=$target-gfortran-posix
    cross_cc=$target-gcc-posix
fi

if [ ! -d $build_dir/openblas_build ]; then
    mkdir -p $build_dir/openblas
    cd $build_dir/openblas
    cp -r $root/third_party/openblas/* .
    make_flags="FC=$cross_fc CC=$cross_cc HOSTCC=gcc MAKE_NB_JOBS=-1 CROSS=1 BUILD_RELAPACK=0 USE_THREAD=0 TARGET=CORE2 DYNAMIC_ARCH=1 ARCH=$blas_arch BINARY=$bits NO_STATIC=1 PREFIX=$build_dir/openblas_build"
    make $make_flags -j$(nproc)
    make $make_flags install
fi

export OpenBLAS_HOME=$build_dir/openblas_build

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

cp -rv $build_dir/openblas_build/* $(pwd)/dist

tar -czvf libtorch-$pkg_suffix.tar.gz --transform 's/^dist/libtorch/' dist/
