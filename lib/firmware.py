import os
import shutil

class Local:

    def __init__(self, base):

        self.base = base

    def create(self, path, content=None):

        if content is None:
            content = []
        elif isinstance(content, str):
            content = [content]

        with open(f"{self.base}/{path}", "w") as local_file:
            local_file.write("".join(content))

    def replace(self, path, changes):

        lines = []

        with open(f"{self.base}/{path}", "r") as local_file:
            for line in local_file.readlines():
                for change in changes:
                    line = line.replace(change[0], change[1])
                lines.append(line)

        with open(f"{self.base}/{path}", "w") as local_file:
            local_file.write("".join(lines))

    def append(self, path, additions):

        if isinstance(additions, str):
            additions = [additions]

        with open(f"{self.base}/{path}", "r") as local_file:
            lines = local_file.readlines()

        for addition in additions:
            if f"{addition}\n" not in lines:
                lines.append(f"{addition}\n")

        with open(f"{self.base}/{path}", "w") as local_file:
            local_file.write("".join(lines))

    def options(self, path, present=None, absent=None):

        if present is None:
            present = []
        elif isinstance(present, str):
            present = [present]

        if absent is None:
            absent = []
        elif isinstance(absent, str):
            absent = [absent]

        with open(f"{self.base}/{path}", "r") as local_file:
            items = local_file.read().split()

        keep = []

        for item in items:
            if item not in absent:
                keep.append(item)

        for item in present:
            if item not in keep:
                keep.append(item)

        with open(f"{self.base}/{path}", "w") as local_file:
            local_file.write(" ".join(keep))

    def directory(self, path):

        if not os.path.exists(f"{self.base}/clot-io/{path}"):
            os.makedirs(f"{self.base}/clot-io/{path}")

    def copy(self, path):

        shutil.copy(path, f"{self.base}/clot-io/{path}")
