#!/bin/bash

if [ -n $1 -o x$1 == x ] ; then
   SERVER_LIST=$1
else
   SERVER_LIST=${SERVER_LIST:="127.0.0.1:2181"}
   echo "Server(s) not specified, using ${SERVER_LIST}"
fi

java -cp ./*:. org.apache.zookeeper.ZooKeeperMain -server "${SERVER_LIST}"
