def local_scheme(version):
    return (
        version.format_with("")
        if version.tag and not version.distance
        else version.format_choice("+{node}", "+{node}.dirty")
    )
