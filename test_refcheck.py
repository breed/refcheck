import unittest

from refcheck import extract_possible_title, extract_possible_author_last_names, extract_possible_year, sanitize_ref


class TestRefCheck(unittest.TestCase):
    test_references = [
        '[3] A. Chowdhery, S. Narang, J. Devlin, M. Bosma, G. Mishra, A. Roberts, P. Barham, H. W. Chung, C. Sutton, S. Gehrmann, et al., "PaLM: Scaling language modeling with pathways," *arXiv preprint*, arXiv:2204.02311, 2022.',
        '[1] A. Ortega, “The Colombian Cacao Sector - 2024 Update,” United States Department of Agriculture (USDA), Bogota, Colombia, Report No. CO2024-0011, Feb. 2024. https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=The%20Colombian%20Cacao%20Sector%20-%202024%20Update Bogota Colombia CO2024-0011.pdf.',
        '[2] W. Phillips-Mora and M. J. Wilkinson, “Frosty Pod of Cacao: A Disease with a Limited Geographic Range but Unlimited Potential for Damage,” Phytopathology, vol. 97, no. 12, pp. 1644–1651, Dec. 2007.',
        '[3] Rola, J. B., Barrera, J. J. A., Calhoun, M. V., Ora˜noMaaghop, J. F., Unajan, M. C., Boncalon, J. M., Sebios, E. T., & Espinosa, J. S. (2024). Convolutional Neural Network Model for Cacao Phytophthora Palmivora Disease Recognition. International Journal of Advanced Computer Science and Applications, vol. 15, no. 8, pp. 986–992, 2024.',
        '[4] D. Buena˜no Vera, B. Oviedo, W. Chiriboga Casanova, and C. Zambrano-Vega, ”Deep Learning-Based Computational Model for Disease Identification in Cocoa Pods (Theobroma cacao L.),” arXiv preprint arXiv:2401.01247, pp. 1–12, 2024.',
        '[5] M. Diarra, K. J. Ayikpa, A. B. Ballo, and B. M. Kouassi, ”Cocoa Pods Diseases Detection by MobileNet Confluence and Classification Algorithms,” International Journal of Advanced Computer Science and Applications, vol. 14, no. 9, pp. 344–352, 2023',
        '[6] M. Dang, H. Wang, Y. Li, and others, ”Computer Vision for Plant Disease Recognition: A Comprehensive Review,” Botanical Review, vol. 90, pp. 251–311, 2024.',
        '[7] P. Sajitha, A. D. Andrushia, N. Anand, and M. Z. Naser, ”A review on machine learning and deep learning image-based plant disease classification for industrial farming systems,” Journal of Industrial Information Integration, vol. 38, 2024.',
        '[8] A. Miracle, ”Enhancing Cocoa Crop Resilience in Ghana: The Application of Convolutional Neural Networks for Early Detection of Disease and Pest Infestations,” Qeios, pp. 1-14, 2024.',
        '[1]Mystakidis, Stylianos. "Metaverse." Encyclopedia 2, no.  1 (2022): 486-497. ',
        '[2]Laeeq, K., 2022. Metaverse: why, how and what. How and What. ',
        '[3]Kerdvibulvech, C., 2022, June. Exploring the impacts of COVID-19 on digital and metaverse games. In  International  conference  on  human-computer  interaction (pp. 561-565). Cham: Springer International  Publishing. ',
        '[4]Chohan, U.W., 2022. Metaverse or Metacurse?.  Available at SSRN 4038770. ',
        '[5]Hazan, S., 2010. Musing the metaverse. Heritage in the Digital Era, Multi-Science Publishing, Brentwood,  Esse, UK. ',
        '[6]Marr, B. (2022, Mar 21). A Short History Of The Metaverse.  Retrieved  from  forbes.com:  https://www.forbes.com/sites/bernardmarr/2022/03/21/a-short-history-of-the-metaverse/?sh=ae88cd759688   ',
        '[7] Talin, B. (2023, Feb 8). History and Evolution of the Metaverse Concept.  Retrieved  from  morethandigital.info:  https://morethandigital.info/en/history-evolution-of-metaverse-concept/ ',
        '[8] Lin, Hong, Shicheng Wan, Wensheng Gan, Jiahui Chen, and  Han-Chieh  Chao.  "Metaverse in education: Vision, opportunities, and challenges." In 2022 IEEE International  Conference on Big Data (Big Data), pp. 2857-2866. IEEE,  2022. ',
        '[9] Niu, X. and Feng, W., 2022, June. Immersive entertainment environments-from theme parks to metaverse. In International Conference on HumanComputer Interaction (pp. 392-403). Cham: Springer  International Publishing. ',
        '[10]Thomason, J., 2021. Metahealth-how will the metaverse change health care?. Journal of Metaverse, 1(1), pp.1316. ',
        '[11] SHREYA. (n.d.). What Are Metaverse Events?- Ideas And Best Practice. Retrieved from taggbox.com:  https://taggbox.com/blog/metaverse-events/ ',
        '[12] PARTNER, B. I. (2022, Feb 8). India\'s first Metaverse wedding had 500 guests, and two brand associations, here\'s how it was executed. Retrieved  from  businessinsider.in:  https://www.businessinsider.in/advertising/ad-tech/article/indias-first-metaverse-wedding-had-500-guests-and-two-brand-associations-heres-how-it-was-executed/articleshow/89423066.cms ',
        '[13] Masih, S. (2023, April 11). How To Buy Property In The Metaverse (Easily).  Retrieved  from  explorateglobal.com:  https://www.explorateglobal.com/blog/buy-property-in-metaverse/#:~:text=How%20To%20Buy%20Property%20In%20The%20Metaverse%3F%201,5%205.%20Confirm%20The%20Property%20You%20Purchased%20  ',
        '[14] Belk, R., Humayun, M. and Brouard, M., 2022. Money, possessions, and ownership in the Metaverse: NFTs, cryptocurrencies, Web3 and Wild Markets. Journal of  Business Research, 153, pp.198-205. ',
        '[15] Wang, Yuntao, Zhou Su, Ning Zhang, Rui Xing,  Dongxiao Liu, Tom H. Luan, and Xuemin Shen. "A survey on metaverse: Fundamentals, security, and privacy." IEEE  Communications  Surveys  &  Tutorials 25, no. 1 (2022): 319-352.      ',
        '[1] X. Wang, L. Sun, A. Chehri, and Y. Song, “A Review of GAN-Based Super-Resolution Reconstruction for Optical Remote Sensing Images,” Remote Sensing, vol. 15, no. 20, Art.  no. 20, Jan. 2023. ',
        '[2] K. Zaluzec, “An Edge Computing Framework for Fusing Geospatial Data Using Laplacian Super Resolution Networks’,”  California State Polytechnic University, Pomona. ',
        '[3] N. Yokoya, “Chapter 2 - Deep learning for super-resolution in remote sensing,” in Advances in Machine Learning and  Image Analysis for GeoAI, S. Prasad, J. Chanussot, and J. Li,  Eds., Elsevier, 2024, pp. 5–26. ',
        '[4] R. Keys, “Cubic convolution interpolation for digital image processing,” IEEE Transactions on Acoustics, Speech, and  Signal Processing, vol. 29, no. 6, pp. 1153–1160, Dec. 1981. ',
        '[5] K. Li, W. Xie, Q. Du, and Y. Li, “DDLPS: Detail-Based Deep Laplacian Pansharpening for Hyperspectral Imagery,”  IEEE Transactions on Geoscience and Remote Sensing, vol. 57,  no. 10, pp. 8011–8025, Oct. 2019. ',
        '[6] R. Wongso, F. A. Luwinda, and Williem, “Evaluation of Deep Super Resolution Methods for Textual Images,” Procedia  Computer Science, vol. 135, pp. 331–337, Jan. 2018. ',
        '[7] G. S. Hundal, C. M. Laux, D. Buckmaster, M. J. Sutton, and M. Langemeier, “Exploring Barriers to the Adoption of Internet of Things-Based Precision Agriculture Practices,” Agriculture,  vol. 13, no. 1, Art. no. 1, Jan. 2023. ',
        '[8] W.-S. Lai, J.-B. Huang, N. Ahuja, and M.-H. Yang, “Fast and Accurate Image Super-Resolution with Deep Laplacian Pyramid Networks,” IEEE Transactions on Pattern Analysis  and Machine Intelligence, vol. PP, Oct. 2017. ',
        '[9] D. Saxena and J. Cao, “Generative Adversarial Networks (GANs): Challenges, Solutions, and Future Directions,” ACM  Comput. Surv., vol. 54, no. 3, p. 63:1-63:42, May 2021. ',
        '[10] Y. Kossale, M. Airaj, and A. Darouichi, “Mode Collapse in Generative Adversarial Networks: An Overview,” in 2022 8th  International Conference on Optimization and Applications  (ICOA), Oct. 2022, pp. 1–6. ',
        '[11] Z. Wang, E. P. Simoncelli, and A. C. Bovik, “Multiscale structural similarity for image quality assessment,” in The  Thrity-Seventh Asilomar Conference on Signals, Systems &  Computers, 2003, Nov. 2003, pp. 1398-1402 Vol.2.  ',
        '[12] J. Cai, B. Huang, and T. Fung, “Progressive spatiotemporal image fusion with deep neural networks,” International Journal  of Applied Earth Observation and Geoinformation, vol. 108, p.  102745, Apr. 2022. ',
        '[13] S. B. Damsgaard, N. J. Hernández Marcano, M.  Nørremark, R. H. Jacobsen, I. Rodriguez, and P. Mogensen, “Wireless Communications for Internet of Farming: An Early 5G Measurement Study,” IEEE Access, vol. 10, pp. 105263– 105277, 2022.    Address for correspondence:  Nicolas Escobedo   3801 W Temple Ave, Pomona, CA   Nescobedo@cpp.edu ',
    ]
    test_years = [
        2022,
        2024,
        2007,
        2024,
        2024,
        2023,
        2024,
        2024,
        2024,
        2022,
        2022,
        2022,
        2022,
        2010,
        2022,
        2023,
        2022,
        2022,
        2021,
        None,
        2022,
        2023,
        2022,
        2022,
        2023,
        None,
        2024,
        1981,
        2019,
        2018,
        2023,
        2017,
        2021,
        2022,
        2003,
        2022,
        2022,
        ]

    test_authors = [
        ["Chowdhery", "Narang", "Devlin", "Bosma", "Mishra", "Roberts", "Barham", "Chung", "Sutton", "Gehrmann"],
        ["Ortega"],
        ["PhillipsMora", "Wilkinson"],
        ["Rola", "Barrera", "Calhoun", "Unajan", "Boncalon", "Sebios", "Espinosa"],
        ["Vera", "Oviedo", "Casanova", "ZambranoVega"],
        ["Diarra", "Ayikpa", "Ballo", "Kouassi"],
        ["Dang", "Wang", "Li"],
        ["Sajitha", "Andrushia", "Anand", "Naser"],
        ["Miracle"],
        ["Mystakidis", "Stylianos"],
        ["Laeeq"],
        ["Kerdvibulvech"],
        ["Chohan"],
        ["Hazan"],
        ["Marr"],
        ["Talin"],
        ["Lin", "Hong", "Wan", "Gan", "Chen", "Chao"],
        ["Niu", "Feng"],
        ["Thomason"],
        [],
        [],
        ["Masih"],
        ["Belk", "Humayun", "Brouard"],
        ["Wang", "Yuntao", "Su", "Zhang", "Xing", "Liu", "Luan", "Shen"],
        ["Wang", "Sun", "Chehri", "Song"],
        ["Zaluzec"],
        ["Yokoya"],
        ["Keys"],
        ["Li", "Xie", "Du", "Li"],
        ["Wongso", "Luwinda", "Williem"],
        ["Hundal", "Laux", "Buckmaster", "Sutton", "Langemeier"],
        ["Lai", "Huang", "Ahuja", "Yang"],
        ["Saxena", "Cao"],
        ["Kossale", "Airaj", "Darouichi"],
        ["Wang", "Simoncelli", "Bovik"],
        ["Cai", "Huang", "Fung"],
        ["Damsgaard", "Marcano", "Jacobsen", "Rodriguez" , 'Mogensen'],
    ]
    test_titles = [
        "PaLM: Scaling language modeling with pathways",
        "The Colombian Cacao Sector - 2024 Update",
        "Frosty Pod of Cacao: A Disease with a Limited Geographic Range but Unlimited Potential for Damage",
        "Convolutional Neural Network Model for Cacao Phytophthora Palmivora Disease Recognition",
        "Deep Learning-Based Computational Model for Disease Identification in Cocoa Pods (Theobroma cacao L.)",
        "Cocoa Pods Diseases Detection by MobileNet Confluence and Classification Algorithms",
        "Computer Vision for Plant Disease Recognition: A Comprehensive Review",
        "A review on machine learning and deep learning image-based plant disease classification for industrial farming systems",
        "Enhancing Cocoa Crop Resilience in Ghana: The Application of Convolutional Neural Networks for Early Detection of Disease and Pest Infestations",
        "Metaverse", "Metaverse: why, how and what",
        "Exploring the impacts of COVID-19 on digital and metaverse games", "Metaverse or Metacurse?",
        "Musing the metaverse", "A Short History Of The Metaverse", "History and Evolution of the Metaverse Concept",
        "Metaverse in education: Vision, opportunities, and challenges",
        "Immersive entertainment environments-from theme parks to metaverse",
        "Metahealth-how will the metaverse change health care?", "What Are Metaverse Events?- Ideas And Best Practice",
        "India\'s first Metaverse wedding had 500 guests, and two brand associations, here\'s how it was executed",
        "How To Buy Property In The Metaverse (Easily)",
        "Money, possessions, and ownership in the Metaverse: NFTs, cryptocurrencies, Web3 and Wild Markets",
        "A survey on metaverse: Fundamentals, security, and privacy",
        "A Review of GAN-Based Super-Resolution Reconstruction for Optical Remote Sensing Images",
        "An Edge Computing Framework for Fusing Geospatial Data Using Laplacian Super Resolution Networks’",
        "Chapter 2 - Deep learning for super-resolution in remote sensing",
        "Cubic convolution interpolation for digital image processing",
        "DDLPS: Detail-Based Deep Laplacian Pansharpening for Hyperspectral Imagery",
        "Evaluation of Deep Super Resolution Methods for Textual Images",
        "Exploring Barriers to the Adoption of Internet of Things-Based Precision Agriculture Practices",
        "Fast and Accurate Image Super-Resolution with Deep Laplacian Pyramid Networks",
        "Generative Adversarial Networks (GANs): Challenges, Solutions, and Future Directions",
        "Mode Collapse in Generative Adversarial Networks: An Overview",
        "Multiscale structural similarity for image quality assessment",
        "Progressive spatiotemporal image fusion with deep neural networks",
        "Wireless Communications for Internet of Farming: An Early 5G Measurement Study",
    ]

    def test_test_data(self):
        self.assertEqual(len(self.test_references), len(self.test_titles))
        self.assertEqual(len(self.test_references), len(self.test_authors))
        self.assertEqual(len(self.test_references), len(self.test_years))

    def test_extract_titles(self):
        for ref, expected_title in zip(self.test_references, self.test_titles):
            (title, rest) = extract_possible_title(sanitize_ref(ref))
            self.assertEqual(expected_title, title)

    def test_extract_authors(self):
        for ref, expected_authors in zip(self.test_references, self.test_authors):
            authors = extract_possible_author_last_names(sanitize_ref(ref))
            self.assertEqual(expected_authors, authors)

    def test_extract_years(self):
        for ref, expected_year in zip(self.test_references, self.test_years):
            year = extract_possible_year(sanitize_ref(ref))
            self.assertEqual(expected_year, year, ref)

if __name__ == '__main__':
    unittest.main()
