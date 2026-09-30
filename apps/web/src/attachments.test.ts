import { describe, expect, it } from 'vitest'
import type { AttachmentFacts } from './api'
import { MAX_BYTES, addFiles, applyFacts } from './attachments'

const file = (name: string, type = 'image/png', size = 10) =>
  new File([new Uint8Array(size)], name, { type })

describe('addFiles', () => {
  it('adds images and PDFs, skipping duplicates', () => {
    const { files, error } = addFiles([file('a.png')], [file('a.png'), file('b.pdf', 'application/pdf')])
    expect(files.map((f) => f.name)).toEqual(['a.png', 'b.pdf'])
    expect(error).toBeUndefined()
  })

  it('stops at the limits with a reason', () => {
    expect(addFiles([file('a.png'), file('b.png'), file('c.png')], [file('d.png')]).error).toBe(
      'Attach at most 3 files.',
    )
    expect(addFiles([], [file('big.png', 'image/png', MAX_BYTES + 1)]).error).toBe('big.png is larger than 5 MB.')
    expect(addFiles([], [file('x.svg', 'image/svg+xml')]).error).toBe("x.svg isn't an image or PDF.")
  })
})

describe('applyFacts', () => {
  const facts = {
    suggested_short_description: 'VPN portal config error',
    description_addendum: 'Error PORTAL_CFG_READ after this morning’s client update.',
  } as AttachmentFacts

  it('keeps a typed title and appends the addendum', () => {
    expect(applyFacts({ short_description: 'VPN broken', description: 'Since 8am.' }, facts)).toEqual({
      short_description: 'VPN broken',
      description: 'Since 8am.\n\nFrom attachments: Error PORTAL_CFG_READ after this morning’s client update.',
    })
  })

  it('uses the suggested title when none was typed', () => {
    expect(applyFacts({ short_description: ' ', description: '' }, facts).short_description).toBe(
      'VPN portal config error',
    )
  })
})
