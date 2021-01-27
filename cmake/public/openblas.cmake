find_package(OpenBLAS QUIET)

if(NOT TARGET caffe2::openblas)
  add_library(caffe2::openblas INTERFACE IMPORTED)
endif()

set_property(
  TARGET caffe2::openblas PROPERTY INTERFACE_INCLUDE_DIRECTORIES
  ${OpenBLAS_INCLUDE_DIR})
set_property(
  TARGET caffe2::openblas PROPERTY INTERFACE_LINK_LIBRARIES
  ${OpenBLAS_LIB})
