#  Copyright 2019 U.C. Berkeley RISE Lab
# 
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
# 
#      http://www.apache.org/licenses/LICENSE-2.0
# 
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

FROM jrafaelsoares/faastcc_base:latest

ARG repo_org=FaaSTCC
ARG source_branch=main
ARG build_branch=docker-build

USER root

# Install kubectl. Downloads a precompiled executable and copies it into place.
RUN wget -O kubectl https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl
RUN chmod +x ./kubectl
RUN mv ./kubectl /usr/local/bin/kubectl

# Create the directory where the kubecfg is stored. The startup scripts will
# copy the actual kubecfg for the cluster into this directory at startup time.
RUN mkdir $HOME/.kube

# NOTE: It doesn't make sense to try to set up the kops user here because the
# person running this may want to configure that specifically. The getting
# started docs link to those instructions explicitly, so we can assume that
# it's done before we get to this point.
WORKDIR $HYDRO_HOME/cluster
RUN git pull --recurse-submodules
RUN git remote remove origin 
RUN git remote add origin https://github.com/$repo_org/cluster
RUN git fetch origin && git checkout -b $build_branch origin/$source_branch
WORKDIR /

RUN pip3 install numpy

COPY start-management.sh /
CMD bash start-management.sh
