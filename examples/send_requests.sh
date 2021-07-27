#!/bin/bash

i=0
while [ $i -lt $1 ]
do
  curl -X POST http://localhost:8000
  let i=i+1
done


#for i in {0..$1}  
#do
 # curl -X POST http://localhost:8000
#done
