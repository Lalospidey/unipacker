import sys
import yara

import r2pipe


class DefaultUnpacker(object):

    def __init__(self, sample):
        self.sample = sample
        r2 = r2pipe.open(sample)
        self.secs = r2.cmdj("iSj")
        ep = r2.cmdj("iej")[0]["vaddr"]
        r2.quit()
        self.allowed_sections = [s["name"] for s in self.secs if
                                 "vaddr" in s and "name" in s and s["vaddr"] <= ep < s["vaddr"] + s["vsize"]]
        self.write_execute_control = False

    def get_tail_jump(self):
        while True:
            try:
                endaddr = input("Define manual end address for emulation (leave empty for max value): ")
                if endaddr == "":
                    return sys.maxsize, None
                endaddr = int(endaddr, 0)
                break
            except ValueError:
                print("Incorrect end address!")
        return endaddr, None

    def get_entrypoint(self):
        while True:
            try:
                startaddr = input(
                    "Define manual start address for emulation or enter ep to use the entry point of the binary: ")
                if startaddr == 'ep' or startaddr == "":
                    return
                else:
                    startaddr = int(startaddr, 0)
                break
            except ValueError:
                print("Incorrect start address!")
        return startaddr

    def get_allowed_addr_ranges(self):
        r2 = r2pipe.open(self.sample)
        sections = r2.cmdj("Sj")
        r2.quit()
        allowed_ranges = []
        for s in sections:
            if 'name' in s:
                if s['name'] in self.allowed_sections:
                    start_addr = s['vaddr']
                    end_addr = s['vsize'] + start_addr
                    allowed_ranges += [(start_addr, end_addr)]
        return allowed_ranges

    def get_section(self, address):
        for s in self.secs:
            if s["vaddr"] <= address < s["vaddr"] + s["vsize"]:
                return s["name"] if "name" in s else "unknown name"
        return "external"

    def get_section_range(self, section):
        for s in self.secs:
            if "name" in s and s["name"] == section:
                return s["vaddr"], s["vaddr"] + s["vsize"]
        return None


class UPXUnpacker(DefaultUnpacker):

    def get_tail_jump(self):
        r2 = r2pipe.open(self.sample)

        ep = r2.cmdj("iej")[0]['vaddr']
        r2.cmd(f"s {ep}")


        upx_saddr, upx_endaddr = self.get_tailjump_helper(r2, ep)


        ep = r2.cmdj("iej")[0]['vaddr']
        r2.cmd(f"s {ep}")

        disass_size = upx_endaddr - ep

        json = r2.cmdj(f"pDj {disass_size}")
        r2.quit()
        i = len(json) - 1
        while i >= 0:
            e = json[i]
            if 'opcode' in e:
                instruction = e['opcode']
                addr = e['offset']
                l_instrcuction = instruction.split()
                if l_instrcuction[0] == 'jmp':
                    oep = int(l_instrcuction[1], 0)
                    if oep < upx_saddr or oep > upx_endaddr:
                        return addr, oep
            i -= 1

        print("Jump to OEP was not found!")
        return super().get_tail_jump()


    def get_tailjump_helper(self, r2,  ep):
        section = r2.cmdj("iSj")
        for s in section:
            if 'name' in s:
                start_addr = s['vaddr']
                end_addr = s['vsize'] + start_addr
                if start_addr <= ep <= end_addr:
                    return start_addr, end_addr


    def get_vaddr_of_section(self, r2, section):
        sections = r2.cmdj("Sj")
        for i in sections:
            if 'name' in i:
                if section == i['name']:
                    start_addr = i['vaddr']
                    end_addr = i['vsize'] + start_addr
                    return start_addr, end_addr

    def get_entrypoint(self):
        return None


class PEtiteUnpacker(DefaultUnpacker):

    def get_entrypoint(self):
        return None

    def get_tail_jump(self):
        return sys.maxsize, None


class ASPackUnpacker(DefaultUnpacker):
    def __init__(self, sample):
        super().__init__(sample)
        self.allowed_sections = ['.aspack']

    def get_entrypoint(self):
        return None

    def get_tail_jump(self):
        return sys.maxsize, None


class FSGUnpacker(DefaultUnpacker):
    def __init__(self, sample):
        super().__init__(sample)
        r2 = r2pipe.open(sample)
        secs = r2.cmdj("iSj")
        self.allowed_sections = []
        for s in secs:
            if "size" in s and s["size"] > 0:
                self.allowed_sections += [s["name"]]
        r2.quit()

    def get_entrypoint(self):
        return None

    def get_tail_jump(self):
        return sys.maxsize, None



def identifypacker(sample, yar):
    rules = yara.compile(filepath=yar)
    matches = rules.match(sample)
    result = generate_label(matches)
    if result == 'unknown':
        print("This packer is unknown. Using default unpacker")
        return 'unknown', matches

    return result, matches


def generate_label(l):
    if 'upx' in str(l):
        return 'upx'
    elif "petite" in str(l):
        return "petite"
    elif 'mew' in str(l):
        return 'mew'
    elif "aspack" in str(l):
        return "aspack"
    elif "fsg" in str(l):
        return "fsg"
    elif "pecompact" in str(l):
        return "pecompact"
    elif "upack" in str(l):
        return "upack"
    else:
        return 'unknown'


def get_unpacker(sample):
    yar = "./packer_signatures.yar"
    packer, yara_matches = identifypacker(sample, yar)
    packers = {
        "upx": UPXUnpacker,
        "petite": PEtiteUnpacker,
        "aspack": ASPackUnpacker,
        "fsg": FSGUnpacker,
    }

    if "pe32" not in str(yara_matches):
        raise RuntimeError("Not a PE32 file!")

    if packer not in packers:
        return DefaultUnpacker(sample), yara_matches
    else:
        return packers[packer](sample), yara_matches
