import { describe, expect, it } from 'vitest'
import { groupCards, loadCollectionCards, parseCards } from './collection'

describe('Wikimasters collection data', () => {
    it('parses the exported collection envelope and nested card fields', () => {
        const cards = parseCards({
            collection: [{
                card: {
                    id: 'card-1',
                    rarity: 'UR',
                    image_url: null,
                    hide_image: false,
                    wikipedia_url: 'https://fr.wikipedia.org/wiki/Exemple',
                    wikipedia_title: 'Exemple',
                },
                tags: [{ name: 'bike' }],
            }],
        })

        expect(cards).toEqual([{
            id: 'card-1',
            name: 'Exemple',
            wikiUrl: 'https://fr.wikipedia.org/wiki/Exemple',
            imageUrl: '',
            tags: ['bike'],
            rarity: 'UR',
            owned: true,
        }])
    })

    it('uses the owned flag for wanted cards and hides restricted images', () => {
        const [card] = parseCards({
            collection: [{
                owned: false,
                card: {
                    id: 'card-2',
                    rarity: 'C',
                    image_url: 'https://example.com/image.jpg',
                    hide_image: true,
                    wikipedia_url: 'https://fr.wikipedia.org/wiki/Autre',
                    wikipedia_title: 'Autre',
                },
                tags: [],
            }],
        })

        expect(card.owned).toBe(false)
        expect(card.imageUrl).toBe('')
    })

    it('loads all matching collection files from the data directory', () => {
        const cards = loadCollectionCards()

        expect(cards.length).toBeGreaterThan(0)
        expect(cards.some((card) => card.name === 'Mads Pedersen' && card.tags.includes('bike') && card.owned)).toBe(true)
    })

    it('loads the top 2020s cyclists as bike wanted cards', () => {
        const names = [
            'Tadej Pogačar',
            'Mathieu van der Poel',
            'Julian Alaphilippe',
            'Jonas Vingegaard',
            'Remco Evenepoel',
            'Wout van Aert',
            'Primož Roglič',
            'Filippo Ganna',
            'Demi Vollering',
            'Lotte Kopecky',
        ]
        const cards = loadCollectionCards().filter((card) => names.includes(card.name))

        expect(cards.map((card) => card.name)).toEqual(names)
        expect(cards.every((card) => card.tags.includes('bike') && !card.owned)).toBe(true)
    })

    it('contains all 40 CAC 40 companies with the 30 missing cards marked unowned', () => {
        const cac40Cards = loadCollectionCards().filter((card) => card.tags.includes('cac40'))

        expect(cac40Cards).toHaveLength(40)
        expect(cac40Cards.filter((card) => !card.owned)).toHaveLength(30)
    })

    it('preserves JSON order for untagged cards regardless of rarity', () => {
        const cards = parseCards({
            collection: ['UR', 'C', 'SR', 'PC', 'R'].map((rarity) => ({
                card: {
                    id: rarity,
                    rarity,
                    wikipedia_url: `https://fr.wikipedia.org/wiki/${rarity}`,
                    wikipedia_title: rarity,
                },
                tags: [],
            })),
        })

        expect(groupCards(cards)[0].cards.map((card) => card.rarity)).toEqual(['UR', 'C', 'SR', 'PC', 'R'])
    })
})