from setuptools import setup

setup(
    name='nionswift_elabftw_plugin',

    version='0.1.2.3.1_pnm_0.9.9.9',

    description='A simple plug-in to allow users to manage \
                their eLabFTW experiments through Nion Swift. \
                (pnm fork)',
    long_description='',

    author='Sherjeel Shabih, Andreas Postl',
    author_email='shabihsherjeel@gmail.com, andreas.postl42@gmail.com',

    license='GNU General Public License v3.0',
    url='https://github.com/shabihsherjeel/nionswift_elabftw_plugin',
    download_url = 'https://github.com/shabihsherjeel/nionswift_elabftw_plugin/archive/v0.1.2.4-alpha.tar.gz',
    keywords = ['NIONSWIFT', 'ELABFTW', 'ELN', 'PLUGIN'],
    packages=['nionswift_plugin.nionswift_elabftw_plugin', 'elabapy'],
    install_requires=['requests', 'cryptography', 'nionutils', 'nionui', 'nionswift', 'pysocks'],
    classifiers=[
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Science/Research',
    'Programming Language :: Python :: 3',
    ],
    include_package_data=True,
    python_requires='~=3.6',
    zip_safe=False,
    )
